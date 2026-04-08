from datetime import datetime
import json
import os
from flask import Blueprint, request, render_template, current_app, flash, redirect, url_for, Response, stream_with_context, send_file
from flask_login import login_required, current_user
from app.models import db, Lecture
from utils.documenter import save_study_notes
from utils.text_extractor import extract_text_from_file
from utils.billing import can_process, spend_credit

processor_bp = Blueprint('processor', __name__)

@processor_bp.route('/dashboard')
@login_required
def dashboard():
    from utils.billing import refresh_user_credits
    refresh_user_credits(current_user)
    lectures = Lecture.query.filter_by(user_id=current_user.id).order_by(Lecture.timestamp.desc()).limit(10).all()
    return render_template('dashboard.html', lectures=lectures)

@processor_bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload_lecture():
    file = request.files.get('lecture_file')
    if not file or file.filename == "":
        return {"status": "error", "message": "No file selected"}, 400
    try:
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)
        return {"status": "success", "filename": file.filename}, 200
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@processor_bp.route('/process-log/<filename>')
@login_required
def process_log(filename):
    custom_title = request.args.get('title') or filename
    export_format = request.args.get('format') or 'pdf'

    def generate():
        # SaaS Credit Check
        if not can_process(current_user):
            yield f"data: {json.dumps({'msg': '❌ OUT OF CREDITS: You have used your 3 daily lectures. Please upgrade to Pro for unlimited access!', 'class': 'text-danger fw-bold'})}\n\n"
            yield f"data: {json.dumps({'message': '____FINISHED____'})}\n\n"
            return
            
        # Deduct credit
        spend_credit(current_user)
        
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        yield f"data: {json.dumps({'msg': '>>> SYSTEM BOOTING: AI PROFESSOR ONLINE', 'class': 'text-info'})}\n\n"
        
        transcript_text = ""
        ext = filename.lower().split('.')[-1]
        
        if ext in ['pdf', 'docx', 'png', 'jpg', 'jpeg', 'webp', 'txt']:
            yield f"data: {json.dumps({'msg': '>>> DETECTED DOCUMENT FORMAT. INITIALIZING AI PROFESSOR...', 'class': 'text-warning'})}\n\n"
            try:
                transcript_text = extract_text_from_file(file_path)
                if transcript_text:
                    yield f"data: {json.dumps({'msg': '✅ TEXT EXTRACTION SUCCESSFUL.', 'class': 'text-success'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'msg': f'❌ EXTRACTION ERROR: {str(e)}', 'class': 'text-danger fw-bold'})}\n\n"
                return
        else:
            from utils.transcriber import transcribe_audio_stream
            try:
                yield f"data: {json.dumps({'msg': '>>> UPLOADING AUDIO TO GROQ WHISPER...', 'class': 'text-warning'})}\n\n"
                for line, final in transcribe_audio_stream(file_path):
                    if line:
                        yield f"data: {json.dumps({'msg': line, 'class': 'text-success'})}\n\n"
                    if final:
                        transcript_text = final
            except Exception as e:
                yield f"data: {json.dumps({'msg': f'❌ TRANSCRIPTION ERROR: {str(e)}', 'class': 'text-danger fw-bold'})}\n\n"
                return

        if not transcript_text or len(transcript_text.strip()) < 3:
            yield f"data: {json.dumps({'msg': '❌ ERROR: No sufficient text detected.', 'class': 'text-danger'})}\n\n"
            return

        summary_text = "" 
        try:
            yield f"data: {json.dumps({'msg': '>>> ANALYZING CONTENT...', 'class': 'text-warning'})}\n\n"
            from utils.summarizer import ai_assistant
            
            summary_chunks = []
            for chunk, final in ai_assistant.get_study_notes(transcript_text):
                if chunk:
                    summary_chunks.append(chunk)
                if final:
                    summary_text = final
            
            if not summary_text and summary_chunks:
                summary_text = "".join(summary_chunks)

        except Exception as e:
            summary_text = f"Summary failed. Error: {str(e)}"
            yield f"data: {json.dumps({'msg': f'⚠️ AI Summary Error: {str(e)}', 'class': 'text-info'})}\n\n"

        try:
            new_lecture = Lecture(
                title=custom_title,
                transcript=transcript_text,
                summary=summary_text,
                output_format=export_format,
                user_id=current_user.id,
                timestamp=datetime.utcnow()
            )
            db.session.add(new_lecture)
            db.session.commit()

            output_filename = f"output_{new_lecture.id}.{export_format}"
            output_path = os.path.join('output', output_filename)
            os.makedirs('output', exist_ok=True)
            
            save_study_notes(summary_text, transcript_text, output_path)
            
            yield f"data: {json.dumps({'msg': '✅ PROCESS COMPLETE.', 'class': 'text-primary fw-bold'})}\n\n"
            yield f"data: {json.dumps({'message': '____FINISHED____'})}\n\n"

        except Exception as e:
            db.session.rollback()
            yield f"data: {json.dumps({'msg': f'❌ SAVE ERROR: {str(e)}', 'class': 'text-danger'})}\n\n"

    response = Response(stream_with_context(generate()), mimetype='text/event-stream')
    response.headers.update({
        'X-Accel-Buffering': 'no',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive'
    })
    return response

@processor_bp.route('/download/<int:lecture_id>')
@login_required
def download_lecture(lecture_id):
    lecture = db.session.get(Lecture, lecture_id)
    if not lecture:
        return "Not found", 404

    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    filename = f"output_{lecture.id}.{lecture.output_format}"
    full_path = os.path.join(root_dir, 'output', filename)

    if os.path.exists(full_path):
        mimetype = 'application/pdf' if lecture.output_format == 'pdf' else 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        return send_file(full_path, as_attachment=True, download_name=f"{lecture.title}.{lecture.output_format}", mimetype=mimetype)
    return "File not found", 404