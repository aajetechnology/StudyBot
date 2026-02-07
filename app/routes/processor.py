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
    custom_title = request.args.get('title') or filename
    export_format = request.args.get('format') or 'pdf'

    def generate():
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
        
        # --- PHASE 1: INITIALIZATION ---
        yield f"data: {json.dumps({'msg': '>>> SYSTEM BOOTING: AI PROFESSOR ONLINE', 'class': 'text-info'})}\n\n"
        
        # --- PHASE 2: TRANSCRIPTION ---
        transcript_text = ""
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

        if not transcript_text:
            yield f"data: {json.dumps({'msg': '❌ ERROR: No text detected in audio.', 'class': 'text-danger'})}\n\n"
            return

        # --- PHASE 3: AI SUMMARIZATION ---
        summary_text = "Summary generation in progress..." 
        try:
            yield f"data: {json.dumps({'msg': '>>> TRANSCRIPTION SUCCESS. ANALYZING CONTENT...', 'class': 'text-warning'})}\n\n"
            from utils.summarizer import ai_assistant
            
            summary_chunks = []
            for chunk, final in ai_assistant.get_study_notes(transcript_text):
                if chunk:
                    summary_chunks.append(chunk)
                    # Send a heartbeat every few chunks so the connection doesn't drop
                    if len(summary_chunks) % 10 == 0:
                        yield f"data: {json.dumps({'msg': 'Professor is writing notes...', 'class': 'text-info small'})}\n\n"
                if final:
                    summary_text = final
            
            # Final fallback to ensure summary_text is NEVER None
            if (summary_text == "Summary generation in progress..." or not summary_text) and summary_chunks:
                summary_text = "".join(summary_chunks)
            elif not summary_text:
                summary_text = "Summary could not be generated."

        except Exception as e:
            summary_text = f"Notice: Summary failed. Error: {str(e)}"
            yield f"data: {json.dumps({'msg': f'⚠️ AI Summary Error: {str(e)}', 'class': 'text-info'})}\n\n"

        # --- PHASE 4: DATABASE & EXPORT ---
        yield f"data: {json.dumps({'msg': '>>> FINALIZING STUDY GUIDE...', 'class': 'text-info'})}\n\n"
        try:
            # Create the record - timestamp uses datetime.utcnow() for standard consistency
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

            # Generate the actual file (PDF/Docx)
            output_filename = f"output_{new_lecture.id}.{export_format}"
            output_path = os.path.join('output', output_filename)
            os.makedirs('output', exist_ok=True)
            
            # Save using your existing documenter utility
            save_study_notes(summary_text, transcript_text, output_path)
            
            yield f"data: {json.dumps({'msg': '✅ ALL SYSTEMS GO. PROCESS COMPLETE.', 'class': 'text-primary fw-bold'})}\n\n"
            yield f"data: {json.dumps({'message': '____FINISHED____'})}\n\n"

        except Exception as e:
            # We catch DB errors specifically so the UI knows why the save failed
            db.session.rollback()
            yield f"data: {json.dumps({'msg': f'❌ DB/SAVE ERROR: {str(e)}', 'class': 'text-danger'})}\n\n"

    # Create Response with streaming headers
    response = Response(stream_with_context(generate()), mimetype='text/event-stream')
    response.headers.update({
        'X-Accel-Buffering': 'no',
        'Cache-Control': 'no-cache',
        'Transfer-Encoding': 'chunked',
        'Connection': 'keep-alive'
    })
    return response


    

@processor_bp.route('/classroom/<int:lecture_id>')
@login_required
def classroom(lecture_id):
    lecture = Lecture.query.get_or_404(lecture_id)
    
    return render_template('classroom.html', lecture=lecture)


@processor_bp.route('/stream-class/<int:lecture_id>')
@login_required
def stream_class(lecture_id):
    lecture = Lecture.query.get_or_404(lecture_id)

    def generate():
        from utils.lecture_mode import start_class_mode_stream
        # 1. Immediate Heartbeat to prevent "Busy" error
        yield f"data: {json.dumps({'msg': '>>> Professor is entering the room...', 'class': 'text-info'})}\n\n"
        
        # 2. Call the AI
        for line, final in start_class_mode_stream(lecture.transcript):
            if line:
                yield f"data: {json.dumps({'msg': line, 'class': 'text-success'})}\n\n"
        
        yield f"data: {json.dumps({'msg': '____FINISHED____'})}\n\n"

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