from datetime import datetime
import json
import os
from flask import Blueprint, request, render_template, current_app, flash, redirect, url_for, Response, stream_with_context, send_file
from flask_login import login_required, current_user
from app.models import db, Lecture
from utils.documenter import save_study_notes

processor_bp = Blueprint('processor', __name__)

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
    

@processor_bp.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    lectures = Lecture.query.filter_by(user_id=current_user.id).order_by(Lecture.id.desc()).all()
    return render_template('dashboard.html', lectures=lectures)

@processor_bp.route('/stream-transcript/<filename>')
@login_required
def stream_transcription(filename):
    file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)

    def generate():
        from utils.transcriber import WhisperModel
        model = WhisperModel("small", device="cpu", compute_type='int8')
        segments, _=model.transcribe(file_path, beam_size=5)

        for segment in segments:
            timestamp = f"[{int(segment.start // 60):02}:{int(segment.start % 60):02}]"
            line = f"{timestamp} {segment.text.strip()}"
            yield f"data: {json.dumps({'message': line})}\n\n"
        yield f"data: {json.dumps({'message': '____FINISHED____'})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')



@processor_bp.route('/process-log/<filename>')
@login_required
def process_log(filename):
    # Capture the custom title and format from the JavaScript URL
    custom_title = request.args.get('title') or filename
    export_format = request.args.get('format') or 'pdf'

    def generate():
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        
        # 1. Transcription
        yield f"data: {json.dumps({'msg': '>>> STARTING TRANSCRIPTION...', 'class': 'text-warning'})}\n\n"
        transcript_text = ""
        from utils.transcriber import transcribe_audio_stream
        for line, final in transcribe_audio_stream(file_path):
            if line:
                yield f"data: {json.dumps({'msg': line, 'class': 'text-success'})}\n\n"
            if final:
                transcript_text = final

        # 2. Summary with Error Handling
        summary = "AI Summary generation failed."
        try:
            yield f"data: {json.dumps({'msg': '>>> GENERATING AI SUMMARY...', 'class': 'text-warning'})}\n\n"
            from utils.summarizer import get_study_notes
            summary = get_study_notes(transcript_text)
        except Exception as e:
            
            print(f"CRITICAL AI ERROR: {str(e)}") 
            
            error_msg = f"AI Error: {str(e)}"
            summary = f"Notice: The transcript was saved, but the summary failed. ({error_msg})"
            yield f"data: {json.dumps({'msg': f'❌ {error_msg}', 'class': 'text-danger fw-bold'})}\n\n"
        
        yield f"data: {json.dumps({'msg': '>>> SAVING TO DATABASE...', 'class': 'text-info'})}\n\n"
        new_lecture = Lecture(
            title=custom_title,
            transcript=transcript_text,
            summary=summary,
            output_format=export_format,
            user_id=current_user.id,
            timestamp=datetime.utcnow()
        )
        db.session.add(new_lecture)
        db.session.commit()

        # 4. Save Physical File
        output_filename = f"output_{new_lecture.id}.{export_format}"
        output_path = os.path.join('output', output_filename)
        os.makedirs('output', exist_ok=True)
        save_study_notes(summary, transcript_text, output_path)
        
        yield f"data: {json.dumps({'msg': '--- PROCESS COMPLETE ---', 'class': 'text-primary fw-bold'})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@processor_bp.route('/download/<int:lecture_id>')
@login_required
def download_lecture(lecture_id):
    lecture = db.session.get(Lecture, lecture_id)
    if not lecture:
        return "Lecture not found", 404

    # Build the absolute path to the file
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    filename = f"output_{lecture.id}.{lecture.output_format}"
    full_path = os.path.join(root_dir, 'output', filename)

    if os.path.exists(full_path):
        return send_file(full_path, as_attachment=True, download_name=f"{lecture.title}.{lecture.output_format}")
    else:
        return f"File not found at: {full_path}", 404
    
def export_as_psf(content_html, output_path):
    with open(output_path, "wb") as f:
        pisa.CreatePDF(content_html, dest=f)