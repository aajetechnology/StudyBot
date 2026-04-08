import json
import base64
import os
import io
import time
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, Response, stream_with_context
from flask_login import login_required, current_user
from app.models import db, Lecture
from groq import Groq
from utils.text_extractor import extract_text_from_file
from utils.billing import can_process, spend_credit
from datetime import datetime, timezone

classroom_bp = Blueprint('classroom', __name__)
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# --- CORE ROUTES ---

@classroom_bp.route('/classroom-selection')
@login_required
def classroom_selection():
    lectures = Lecture.query.filter_by(user_id=current_user.id).order_by(Lecture.timestamp.desc()).all()
    return render_template('classroom_selection.html', lectures=lectures)

@classroom_bp.route('/start-class', methods=['POST'])
@login_required
def start_class():
    if not can_process(current_user):
        flash("Out of Credits! You have used your 3 daily lectures. Please upgrade to Pro!", "danger")
        return redirect(url_for('classroom.classroom_selection'))

    files = request.files.getlist('doc_file')
    
    if not files or all(f.filename == '' for f in files):
        flash("Please upload a document to start the class.", "warning")
        return redirect(url_for('classroom.classroom_selection'))

    combined_text = ""
    for file in files:
        if file.filename == '': continue
        try:
            text = extract_text_from_file(file)
            if text and len(text.strip()) > 0:
                combined_text += text + "\n"
                print(f"✅ Extracted {len(text)} chars from {file.filename}")
            else:
                print(f"⚠️ Extraction returned no text for {file.filename}")
        except Exception as e:
            print(f"❌ Extraction error for {file.filename}: {e}")

    if len(combined_text.strip()) < 20:
        flash("The AI couldn't read those notes. Try a clearer file!", "danger")
        return redirect(url_for('classroom.classroom_selection'))

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
        spend_credit(current_user) # Deduct credit
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

    raw_content = lecture.transcript or  lecture.summary or ""
    global_map = generate_global_summary(raw_content)
    
    syllabus_prompt = f"""
    Based on this Knowledge Map, break the lecture into 4-8 logically sequenced modules. 
    For each module, provide a title and a 3-word 'search_query' for the original text.
    Return ONLY JSON: {{ "modules": [ {{ "title": "...", "query": "..." }}, ... ] }}
    
    Knowledge Map: {global_map} 
    """
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user",  "content": syllabus_prompt}],
            response_format ={"type": "json_object"})

        syllabus_data =json.loads( completion.choices[0].message.content)
        session['classroom_syllabus'] = syllabus_data.get('modules', [])
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

    return render_template('classroom.html', 
                           module_title=syllabus[step]['title'] if isinstance(syllabus[step], dict) else syllabus[step],
                           step=step + 1,
                           total_steps=len(syllabus),
                           lecture_id=lecture_id)


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

def find_relevant_chunk(full_text, query, window_size=15000):
    import re
    if not query: return full_text[:window_size]

    match = re.search(re.escape(query.lower()), full_text.lower())
    if match:
        start = max(0, match.start() - 2000)
        end = min(len(full_text), start + window_size)
        return full_text[start:end]
    return full_text[:window_size]
        

@classroom_bp.route('/stream-module-content')
@login_required
def stream_module_content():
    lecture_id = session.get('classroom_lecture_id')
    step = session.get('classroom_step', 0)
    syllabus = session.get('classroom_syllabus', []) 
    
    lecture = db.session.get(Lecture, lecture_id)
    raw_content = lecture.transcript or ""
    
    current_module = syllabus[step] if step < len(syllabus) else {"title": "Summary", "query": ""}
    
    context_chunk = find_relevant_chunk(raw_content, current_module.get('query'))
    def generate():
        try:
            system_instruction = """
            You are 'Professor StudyBot', a world-class Socratic teacher. 
            Your goal is to make the student UNDERSTAND, not just read.
            
            Follow this strict teaching flow:
            1. THE HOOK: Why does this specific module matter in the real world? (1-2 sentences)
            2. THE ANALOGY: Explain the core concept using a simple, relatable story.
            3. THE DEEP DIVE: Use the provided context to explain the technical details clearly in Markdown.
            4. THE CHECKPOINT: End with a friendly question asking if they want a deeper dive or a simpler example.
            """
            
            response_stream = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": f"Teach Module: {current_module['title']}. \n\nContext from PDF: {context_chunk}"}
                ],
                stream=True
            )
            for chunk in response_stream:
                if chunk.choices[0].delta.content:
                    yield f"data: {json.dumps({'msg': chunk.choices[0].delta.content})}\n\n"
            
            yield f"data: {json.dumps({'msg': '____FINISHED____'})}\n\n"
                    
        except Exception as e:
            yield f"data: {json.dumps({'msg': f'❌ Error: {str(e)}'})}\n\n"
    return Response(stream_with_context(generate()), mimetype='text/event-stream')
    
def generate_global_summary(full_text):
    """Scans and summarizes large documents in chunks to create a Knowledge Map."""
    chunk_size = 15000  # ~2500 words per chunk
    overlap = 1000
    chunks = []
    
    # Split text into chunks
    for i in range(0, len(full_text), chunk_size - overlap):
        chunks.append(full_text[i:i + chunk_size])
    
    # We take up to 20 segments (covers about 150-200 pages)
    chunk_summaries = []
    for idx, chunk in enumerate(chunks[:20]): 
        prompt = f"Summarize the key educational topics in this section of the document. Part {idx+1}:\n\n{chunk}"
        try:
            # Using a faster model for intermediate steps to save time
            completion = client.chat.completions.create(
                model="llama-3.1-8b-instant", 
                messages=[{"role": "user", "content": prompt}]
            )
            chunk_summaries.append(completion.choices[0].message.content)
        except:
            continue
            
    # Combine summaries into a final Knowledge Map
    combined_summary = "\n\n".join(chunk_summaries)
    final_prompt = f"""
    Create a detailed Knowledge Map of this entire document based on these summaries. 
    Identify the main themes and the order of topics.
    Summaries: {combined_summary}
    """
    
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": final_prompt}]
        )
        return completion.choices[0].message.content
    except:
        return full_text[:15000] # Fallback if AI fails
