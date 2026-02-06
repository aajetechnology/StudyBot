import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user
from app.models import db, Lecture
from utils.summarizer import ai_assistant

classroom_bp = Blueprint('classroom', __name__)

@classroom_bp.route('/classroom-selection')
@login_required
def classroom_selection():
    """Page to select which lecture to be taught."""
    lectures = Lecture.query.filter_by(user_id=current_user.id).order_by(Lecture.timestamp.desc()).all()
    return render_template('classroom_selection.html', lectures=lectures)

@classroom_bp.route('/init-class/<int:lecture_id>')
@login_required
def init_class(lecture_id):
    """Analyze the lecture and divide it into learning modules."""
    lecture = db.session.get(Lecture, lecture_id)
    if not lecture:
        flash("Lecture not found.", "danger")
        return redirect(url_for('classroom.classroom_selection'))

    # Prompt AI to create a syllabus/table of contents
    syllabus_prompt = f"""
    You are an expert curriculum designer. Break the following lecture content into a logical sequence of 4 to 6 learning modules.
    Return ONLY a JSON object with a 'modules' key containing a list of strings (titles).
    Lecture Title: {lecture.title}
    Content: {lecture.transcript[:5000]}
    """

    try:
        completion = ai_assistant.client.chat.completions.create(
            model=ai_assistant.model,
            messages=[{"role": "user", "content": syllabus_prompt}],
            response_format={"type": "json_object"}
        )
        syllabus = json.loads(completion.choices[0].message.content)
        
        # Save syllabus and progress in session
        session['classroom_syllabus'] = syllabus.get('modules', ["Introduction", "Core Concepts", "Summary"])
        session['classroom_step'] = 0
        session['classroom_lecture_id'] = lecture_id
        
        return redirect(url_for('classroom.teach_module'))
    except Exception as e:
        flash("Could not initialize classroom. Try again.", "danger")
        return redirect(url_for('classroom.classroom_selection'))

@classroom_bp.route('/teach')
@login_required
def teach_module():
    """The main teaching interface for the current module."""
    lecture_id = session.get('classroom_lecture_id')
    step = session.get('classroom_step', 0)
    syllabus = session.get('classroom_syllabus', [])

    if not lecture_id or step >= len(syllabus):
        flash("Class session ended or not found.", "info")
        return redirect(url_for('classroom.classroom_selection'))

    lecture = db.session.get(Lecture, lecture_id)
    current_module_title = syllabus[step]

    # AI Teaching Prompt
    teach_prompt = f"""
    You are a supportive and detailed AI Professor. 
    Explain the module: "{current_module_title}" based on the lecture: "{lecture.title}".
    
    Guidelines:
    1. Provide a detailed, easy-to-understand explanation of this specific part.
    2. Use analogies if the concept is complex.
    3. Suggest one relevant YouTube search term.
    4. Recommend one book for further reading.
    5. Ask the student if they understand or want a test.

    Content context: {lecture.transcript[:8000]}
    """

    try:
        completion = ai_assistant.client.chat.completions.create(
            model=ai_assistant.model,
            messages=[{"role": "user", "content": teach_prompt}]
        )
        explanation = completion.choices[0].message.content
        
        return render_template('classroom_view.html', 
                               explanation=explanation, 
                               module_title=current_module_title,
                               step=step + 1,
                               total_steps=len(syllabus),
                               lecture_id=lecture_id)
    except Exception as e:
        flash("Teacher is having trouble. Please refresh.", "warning")
        return redirect(url_for('classroom.classroom_selection'))

@classroom_bp.route('/ask-tutor', methods=['POST'])
@login_required
def ask_tutor():
    """Handle student questions during a module."""
    user_question = request.form.get('question')
    module_title = request.form.get('module_title')
    lecture_id = session.get('classroom_lecture_id')
    
    lecture = db.session.get(Lecture, lecture_id)
    
    answer_prompt = f"""
    The student is learning about "{module_title}" from the lecture "{lecture.title}".
    They have a question: "{user_question}".
    Answer them clearly based on this context: {lecture.transcript[:4000]}
    """

    try:
        completion = ai_assistant.client.chat.completions.create(
            model=ai_assistant.model,
            messages=[{"role": "user", "content": answer_prompt}]
        )
        answer = completion.choices[0].message.content
        return {"answer": answer}
    except:
        return {"answer": "I'm sorry, I couldn't process that question right now."}

@classroom_bp.route('/next-module')
@login_required
def next_module():
    """Move to the next part of the lecture."""
    session['classroom_step'] = session.get('classroom_step', 0) + 1
    return redirect(url_for('classroom.teach_module'))