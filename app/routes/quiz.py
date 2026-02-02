import os
import json
import pdfplumber
from docx import Document
from datetime import datetime, timezone # Use timezone-aware dates
from flask import Blueprint, render_template, request, redirect, url_for, current_app, flash, session
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.models import db, Lecture, Quiz  
# FIXED: Import the assistant class instance from the app package
from utils.summarizer import ai_assistant

quiz_bp = Blueprint('quiz', __name__)

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

@quiz_bp.route('/quiz-selection')
@login_required
def quiz_selection():
    lectures = Lecture.query.filter_by(user_id=current_user.id).order_by(Lecture.timestamp.desc()).all()
    return render_template('quiz_selection.html', lectures=lectures)

@quiz_bp.route('/start-quiz', methods=['POST'])
@login_required
def start_quiz():
    num_questions = int(request.form.get('count', 10))

    if 'doc_file' in request.files and request.files['doc_file'].filename != "":
        file = request.files['doc_file']
        filename = secure_filename(file.filename)
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        extracted_text = extract_text_from_file(filepath)
        if len(extracted_text.strip()) < 50:
            flash("The document is too short or empty for a quiz!", 'danger')
            return redirect(url_for('quiz.quiz_selection'))
        
        # FIXED: Use timezone-aware UTC
        new_lecture = Lecture(
            title=filename,
            transcript=extracted_text,
            summary="Direct Quiz Upload",
            timestamp=datetime.now(timezone.utc), 
            user_id=current_user.id
        )
        db.session.add(new_lecture)
        db.session.commit()
        lecture_id = new_lecture.id
    else:
        lecture_id = request.form.get('lecture_id')
        if not lecture_id:
            flash('Please select a document or upload a new one.', 'warning')
            return redirect(url_for('quiz.quiz_selection'))
    
    return redirect(url_for('quiz.run_exam', lecture_id=lecture_id, count=num_questions))

@quiz_bp.route('/run-exam/<int:lecture_id>/<int:count>')
@login_required
def run_exam(lecture_id, count):
    lecture = db.session.get(Lecture, lecture_id)
    if not lecture:
        flash("Lecture not found.", "danger")
        return redirect(url_for('quiz.quiz_selection'))

    # Calculate timer based on content type
    math_keywords = ['=', '+', '/', '*', 'calculate', 'solve', 'formula', 'x', 'y', 'total']
    is_calc = any(word in lecture.transcript.lower() for word in math_keywords)
    total_seconds = count * (180 if is_calc else 90)

    prompt = f"""
    Generate a quiz with exactly {count} questions based on this text.
    Mix multiple choice (objective) and 2-3 short theory questions.
    Return ONLY a valid JSON object.
    {{
        "questions": [
            {{"id": 1, "type": "objective", "q": "Question text", "options": ["A", "B", "C", "D"], "ans": "A"}},
            {{"id": 2, "type": "theory", "q": "Theory question", "keywords": ["key1", "key2"]}}
        ]
    }}
    Text: {lecture.transcript[:6000]} 
    """

    try:
        # FIXED: Use the ai_assistant instance instead of raw client
        completion = ai_assistant.client.chat.completions.create(
            model=ai_assistant.model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        quiz_data = json.loads(completion.choices[0].message.content)
        session['current_quiz'] = quiz_data['questions']
        
    except Exception as e:
        current_app.logger.error(f"Quiz AI error: {str(e)}")
        flash("AI failed to generate quiz. Please try a different document.", "danger")
        return redirect(url_for('quiz.quiz_selection'))

    return render_template('cbt_exam.html', 
                           quiz=quiz_data['questions'], 
                           lecture=lecture,
                           timer=total_seconds,
                           count=count)

@quiz_bp.route('/submit-quiz', methods=['POST'])
@login_required
def submit_quiz():
    lecture_id = request.form.get('lecture_id')
    quiz_questions = session.get('current_quiz')
    
    if not quiz_questions:
        flash("Quiz session expired. Please restart.", "danger")
        return redirect(url_for('quiz.quiz_selection'))

    user_answers = {}
    score = 0
    failed_qs = []

    for i, q in enumerate(quiz_questions):
        user_ans = request.form.get(f'ans-{i}', "").strip()
        user_answers[str(i)] = user_ans
        
        if q['type'] == 'objective':
            if user_ans == q.get('ans'):
                score += 1
            else:
                failed_qs.append(q['q'])
        else:
            # Theory keyword matching
            if any(word.lower() in user_ans.lower() for word in q.get('keywords', [])):
                score += 1
            else:
                failed_qs.append(q['q'])

    # AI Tutor Feedback
    advice_prompt = f"The student took a quiz and failed these topics: {failed_qs[:3]}. Give a brief Study Tip and a YouTube search term for them."
    try:
        completion = ai_assistant.client.chat.completions.create(
            model=ai_assistant.model,
            messages=[{"role": "user", "content": advice_prompt}]
        )
        tutor_advice = completion.choices[0].message.content
    except:
        tutor_advice = "Focus on the key concepts mentioned in the lecture notes and try again!"

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
    
    # Clear session to prevent resubmission
    session.pop('current_quiz', None)

    return redirect(url_for('quiz.view_results', quiz_id=new_result.id))

@quiz_bp.route('/results/<int:quiz_id>')
@login_required
def view_results(quiz_id):
    quiz = db.session.get(Quiz, quiz_id)
    if not quiz or quiz.user_id != current_user.id:
        flash("Result not found.", "danger")
        return redirect(url_for('quiz.quiz_selection'))
    return render_template('quiz_results.html', quiz=quiz)