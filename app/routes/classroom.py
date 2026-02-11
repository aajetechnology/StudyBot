import json
import base64
import os
import io
import time
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, Response, stream_with_context
from flask_login import login_required, current_user
from app.models import db, Lecture
from groq import Groq
from pypdf import PdfReader
import pypdfium2 as pdfium

classroom_bp = Blueprint('classroom', __name__)
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# --- UTILITY FUNCTIONS (OCR & VISION) ---

def call_groq_vision(base64_image, prompt_text):
    try:
        response = client.chat.completions.create(
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt_text},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
            }],
            model="llama-3.2-11b-vision-preview",
        )
        return response.choices[0].message.content + "\n"
    except Exception as e:
        return f"\n[Vision Error: {str(e)}]\n"

def extract_text_from_file(file):
    filename = file.filename.lower()
    extracted_text = ""
    if filename.endswith('.pdf'):
        reader = PdfReader(file)
        for page in reader.pages:
            extracted_text += page.extract_text() or ""
        
        if len(extracted_text.strip()) < 50:
            file.seek(0)
            pdf = pdfium.PdfDocument(file)
            for i in range(min(5, len(pdf))):
                page = pdf[i]
                bitmap = page.render(scale=2)
                pil_image = bitmap.to_pil()
                img_byte_arr = io.BytesIO()
                pil_image.save(img_byte_arr, format='JPEG')
                base64_image = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
                extracted_text += call_groq_vision(base64_image, "Extract lecture text.")
            pdf.close()
    elif filename.endswith(('.png', '.jpg', '.jpeg')):
        image_bytes = file.read()
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        extracted_text = call_groq_vision(base64_image, "Transcribe perfectly.")
    return extracted_text

# --- CORE ROUTES ---

@classroom_bp.route('/classroom-selection')
@login_required
def classroom_selection():
    lectures = Lecture.query.filter_by(user_id=current_user.id).order_by(Lecture.timestamp.desc()).all()
    return render_template('classroom_selection.html', lectures=lectures)



from datetime import datetime, timezone

@classroom_bp.route('/start-class', methods=['POST'])
@login_required
def start_class():
    files = request.files.getlist('doc_file')
    
    if not files or all(f.filename == '' for f in files):
        flash("Please upload a document to start the class.", "warning")
        return redirect(url_for('classroom.classroom_selection'))

    combined_text = ""
    for file in files:
        if file.filename == '': continue
        try:
            # We use the utility function you already have in this file
            text = extract_text_from_file(file)
            combined_text += text + "\n"
        except Exception as e:
            print(f"Extraction error: {e}")

    if len(combined_text.strip()) < 20:
        flash("The AI couldn't read those notes. Try a clearer file!", "danger")
        return redirect(url_for('classroom.classroom_selection'))

    # Create the Lecture record
    new_lecture = Lecture(
        title=files[0].filename[:50],
        transcript=combined_text,
        summary="Classroom notes generated from upload.",
        user_id=current_user.id,
        timestamp=datetime.now(timezone.utc)
    )
    
    try:
        db.session.add(new_lecture)
        db.session.commit()
        # SUCCESS: Now send them to the Classroom Init logic
        return redirect(url_for('classroom.init_class', lecture_id=new_lecture.id))
    except Exception as e:
        db.session.rollback()
        flash("Database error occurred.", "danger")
        return redirect(url_for('classroom.classroom_selection'))
    
    
@classroom_bp.route('/init-class/<int:lecture_id>')
@login_required
def init_class(lecture_id):
    lecture = db.session.get(Lecture, lecture_id)
    if not lecture:
        flash("Lecture not found.", "danger")
        return redirect(url_for('classroom.classroom_selection'))

    # Logic: Try transcript first, then content (PDF/OCR), then summary.
    raw_content = lecture.transcript or getattr(lecture, 'content', None) or lecture.summary
    
    if not raw_content:
        flash("This lecture has no content to teach from.", "warning")
        return redirect(url_for('classroom.classroom_selection'))

    syllabus_prompt = f"Break this lecture into 4-6 modules. Return ONLY JSON with a key 'modules' (list of strings). Content: {raw_content[:4000]}"

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": syllabus_prompt}],
            response_format={"type": "json_object"}
        )
        syllabus = json.loads(completion.choices[0].message.content)
        
        session['classroom_syllabus'] = syllabus.get('modules', ["Introduction", "Core Concepts", "Summary"])
        session['classroom_step'] = 0
        session['classroom_lecture_id'] = lecture_id
        
        return redirect(url_for('classroom.teach_module'))
    except Exception as e:
        flash(f"Classroom Init Failed: {str(e)}", "danger")
        return redirect(url_for('classroom.classroom_selection'))

@classroom_bp.route('/teach')
@login_required
def teach_module():
    lecture_id = session.get('classroom_lecture_id')
    step = session.get('classroom_step', 0)
    syllabus = session.get('classroom_syllabus', [])

    if not lecture_id or step >= len(syllabus):
        return redirect(url_for('classroom.classroom_selection'))

    return render_template('classroom_view.html', 
                           module_title=syllabus[step],
                           step=step + 1,
                           total_steps=len(syllabus),
                           lecture_id=lecture_id)

@classroom_bp.route('/stream-module-content')
@login_required
def stream_module_content():
    lecture_id = session.get('classroom_lecture_id')
    step = session.get('classroom_step', 0)
    syllabus = session.get('classroom_syllabus', [])
    
    lecture = db.session.get(Lecture, lecture_id)
    if not lecture:
        return Response("data: " + json.dumps({"msg": "❌ Lecture not found."}) + "\n\n", mimetype='text/event-stream')

    # SYNC FIX: Ensure we check both transcript and content
    raw_content = lecture.transcript or getattr(lecture, 'content', None) or lecture.summary or "No notes found."
    current_module_title = syllabus[step] if step < len(syllabus) else "Discussion"

    def generate():
        try:
            yield f"data: {json.dumps({'msg': '>>> The Professor is checking the notes...', 'class': 'text-info'})}\n\n"
            
            response_stream = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "You are an engaging Professor. Teach the module clearly using Markdown. Use bolding and lists for readability."},
                    {"role": "user", "content": f"Teach Module: {current_module_title}. Context: {raw_content[:12000]}"}
                ],
                stream=True
            )

            for chunk in response_stream:
                if chunk.choices[0].delta.content:
                    yield f"data: {json.dumps({'msg': chunk.choices[0].delta.content})}\n\n"
            
            yield f"data: {json.dumps({'msg': '____FINISHED____'})}\n\n"
                    
        except Exception as e:
            yield f"data: {json.dumps({'msg': f'❌ Professor Error: {str(e)}'})}\n\n"

    # CRITICAL: Headers to ensure real-time delivery
    response = Response(stream_with_context(generate()), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no' 
    response.headers['Connection'] = 'keep-alive'
    return response

@classroom_bp.route('/ask-tutor', methods=['POST'])
@login_required
def ask_tutor():
    question = request.form.get('question', '')
    module_title = request.form.get('module_title', '')
    
    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": f"You are a Professor teaching: {module_title}"},
            {"role": "user", "content": question}
        ],
        model="llama-3.3-70b-versatile",
    )
    return jsonify({"answer": response.choices[0].message.content})

@classroom_bp.route('/next-module')
@login_required
def next_module():
    session['classroom_step'] = session.get('classroom_step', 0) + 1
    return redirect(url_for('classroom.teach_module'))