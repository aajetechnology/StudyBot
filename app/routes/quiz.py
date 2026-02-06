import os
import json
import base64
import io
import pdfplumber
from pypdf import PdfReader
from docx import Document
from datetime import datetime, timezone
from flask import Blueprint, render_template, request, redirect, url_for, current_app, flash, session, jsonify
from flask_login import login_required, current_user
from rapidfuzz import fuzz
from groq import Groq

from app.models import db, Lecture, Quiz  
from utils.summarizer import ai_assistant

quiz_bp = Blueprint('quiz', __name__)
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# --- HELPER FUNCTIONS ---

def extract_text_from_file(filepath):
    """Securely extract text from various file formats."""
    ext = filepath.rsplit('.', 1)[1].lower()
    text = ""
    try:
        if ext == "pdf":
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    pagetext = page.extract_text()
                    if pagetext:
                        text += pagetext + "\n"
        elif ext == 'docx':
            doc = Document(filepath)
            for para in doc.paragraphs:
                text += para.text + "\n"
        elif ext == 'txt':
            with open(filepath, 'r', encoding='utf-8') as f:
                text = f.read()
        return text
    except Exception as e:
        current_app.logger.error(f"File extraction error: {str(e)}")
        return ""

# --- ROUTES ---

@quiz_bp.route('/quiz-selection')
@login_required
def quiz_selection():
    lectures = Lecture.query.filter_by(user_id=current_user.id).order_by(Lecture.timestamp.desc()).all()
    return render_template('quiz_selection.html', lectures=lectures)

@quiz_bp.route('/start-quiz', methods=['POST'])
@login_required
def start_quiz():
    files = request.files.getlist('doc_file')
    
    if not files or files[0].filename == '':
        flash("Please upload at least one PDF or photo of your notes!", "warning")
        return redirect(request.url)

    combined_text = ""
    for file in files:
        filename = file.filename.lower()
        
        # --- PDF EXTRACTION ---
        if filename.endswith('.pdf'):
            reader = PdfReader(file)
            page_text = ""
            for page in reader.pages:
                page_text += page.extract_text() or ""
            
            if len(page_text.strip()) < 50:
                combined_text += "[Scanned PDF detected - AI will summarize context]\n"
            else:
                combined_text += page_text + "\n"
        
        # --- IMAGE/PHOTO EXTRACTION ---
        elif filename.endswith(('.png', '.jpg', '.jpeg')):
            image_bytes = file.read()
            encoded_image = base64.b64encode(image_bytes).decode('utf-8')
            try:
                vision_completion = client.chat.completions.create(
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Extract all academic text from this image perfectly so I can teach a student from it."},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded_image}"}}
                        ]
                    }],
                    model="llama-3.2-11b-vision-preview",
                )
                combined_text += vision_completion.choices[0].message.content + "\n"
            except Exception as e:
                current_app.logger.error(f"Vision Error: {e}")

    # Safety Check: Did we get anything?
    if len(combined_text.strip()) < 20:
        flash("The AI couldn't read the notes. Please ensure the photos are clear!", "danger")
        return redirect(url_for('quiz.quiz_selection'))

    # FIXED: Using 'transcript' instead of 'content' to match your Model
    new_lecture = Lecture(
        title=files[0].filename[:50],
        transcript=combined_text,  # <--- This matches your SQLAlchemy column
        user_id=current_user.id,
        timestamp=datetime.now(timezone.utc)
    )
    
    try:
        db.session.add(new_lecture)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Database Save Error: {e}")
        flash("Failed to save lecture to database.", "danger")
        return redirect(url_for('quiz.quiz_selection'))

    return redirect(url_for('classroom.init_class', lecture_id=new_lecture.id))


@quiz_bp.route('/run-exam/<int:lecture_id>/<int:count>')
@login_required
def run_exam(lecture_id, count):
    lecture = db.session.get(Lecture, lecture_id)
    if not lecture:
        flash("Lecture not found.", "danger")
        return redirect(url_for('quiz.quiz_selection'))

    # Use content if transcript is missing (for PDF/Photo uploads)
    raw_text = lecture.transcript if lecture.transcript else lecture.content
    if not raw_text:
        flash("No content found to generate a quiz.", "warning")
        return redirect(url_for('quiz.quiz_selection'))

    # Determine timer duration
    math_keywords = ['=', '+', '/', '*', 'calculate', 'solve', 'formula', 'x', 'y']
    is_calc = any(word in raw_text.lower() for word in math_keywords)
    total_seconds = count * (180 if is_calc else 90)

    prompt = f"""
    Generate a quiz with exactly {count} questions based on this text.
    Mix multiple choice (objective) and 2-3 short theory questions.
    Return ONLY a valid JSON object.
    {{
        "questions": [
            {{"id": 1, "type": "objective", "q": "Question text", "options": ["Choice1", "Choice2", "Choice3", "Choice4"], "ans": "Choice1"}},
            {{"id": 2, "type": "theory", "q": "Theory question", "keywords": ["word1", "word2"]}}
        ]
    }}
    CRITICAL: For 'objective' questions, 'ans' must be the FULL TEXT of the correct option.
    Text: {raw_text[:6000]}
    """

    try:
        completion = ai_assistant.client.chat.completions.create(
            model=ai_assistant.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        quiz_data = json.loads(completion.choices[0].message.content)
        session['current_quiz'] = quiz_data['questions']
        
        return render_template('cbt_exam.html', 
                               quiz=quiz_data['questions'], 
                               lecture=lecture,
                               timer=total_seconds,
                               count=count)
    except Exception as e:
        current_app.logger.error(f"Quiz AI error: {str(e)}")
        flash("AI failed to generate quiz. Please try again.", "danger")
        return redirect(url_for('quiz.quiz_selection'))

@quiz_bp.route('/submit-quiz', methods=['POST'])
@login_required
def submit_quiz():
    lecture_id = request.form.get('lecture_id')
    quiz_questions = session.get('current_quiz')
    
    if not quiz_questions:
        flash("Quiz session expired.", "danger")
        return redirect(url_for('quiz.quiz_selection'))

    user_answers = {}
    score = 0
    failed_qs = []

    for i, q in enumerate(quiz_questions):
        user_ans = request.form.get(f'ans-{i}', "").strip().lower()
        correct_ans = str(q.get('ans', "")).strip().lower()
        user_answers[str(i)] = user_ans

        if q['type'] == 'objective':
            if fuzz.token_set_ratio(user_ans, correct_ans) > 90:
                score += 1
            else:
                failed_qs.append(q['q'])
        else:
            keywords = [k.lower() for k in q.get('keywords', [])]
            found = [w for w in keywords if w in user_ans]
            if len(keywords) > 0 and len(found) >= (len(keywords) / 2):
                score += 1
            else:
                failed_qs.append(q['q'])
        
    # Generate Feedback
    advice_prompt = f"Student scored {score}/{len(quiz_questions)}. Failed topics: {failed_qs[:2]}. Give a 2-sentence tip and a YouTube search term."
    try:
        fb = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": advice_prompt}]
        )
        tutor_advice = fb.choices[0].message.content
    except:
        tutor_advice = "Good job! Keep studying your notes."

    new_result = Quiz(
        lecture_id=lecture_id,
        user_id=current_user.id,
        score=score,
        total_questions=len(quiz_questions),
        questions_json=json.dumps(quiz_questions),
        user_answers=json.dumps(user_answers),
        feedback=tutor_advice
    )
    db.session.add(new_result)
    db.session.commit()
    session.pop('current_quiz', None)

    return redirect(url_for('quiz.view_results', quiz_id=new_result.id))

@quiz_bp.route('/results/<int:quiz_id>')
@login_required
def view_results(quiz_id):
    quiz = db.session.get(Quiz, quiz_id)
    if not quiz or quiz.user_id != current_user.id:
        return redirect(url_for('quiz.quiz_selection'))
    
    questions = json.loads(quiz.questions_json)
    user_answers = json.loads(quiz.user_answers)
    quiz_details = []

    for i, q in enumerate(questions):
        u_ans = user_answers.get(str(i), "No Answer")
        if q['type'] == 'objective':
            is_correct = fuzz.token_set_ratio(u_ans.lower(), str(q.get('ans', "")).lower()) > 90
            correct_display = q.get('ans')
        else:
            keywords = [k.lower() for k in q.get('keywords', [])]
            found = [w for w in keywords if w in u_ans.lower()]
            is_correct = len(found) >= (len(keywords)/2) and len(keywords) > 0
            correct_display = "Keywords: " + ", ".join(q.get('keywords', []))
        
        quiz_details.append({
            'question': q['q'],
            'user_answer': u_ans,
            'correct_answer': correct_display,
            'is_correct': is_correct
        })

    return render_template('quiz_results.html', quiz=quiz, quiz_details=quiz_details)