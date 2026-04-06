from flask import Blueprint, render_template, request, jsonify, session
from flask_login import login_required
from app.models import Lecture, db 
import os
from groq import Groq


client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

chatproff_bp = Blueprint('chatproff', __name__)

@chatproff_bp.route('/professor-office')
@login_required
def professor_office():
    # Get the last lecture to provide context for the "Office Hours"
    lecture_id = session.get('classroom_lecture_id')
    lecture = db.session.get(Lecture, lecture_id) if lecture_id else None
    return render_template('chatproff.html', lecture=lecture)

@chatproff_bp.route('/chat-professor', methods=['POST'])
@login_required
def chat_professor():
    user_message = request.json.get('message')
    lecture_id = session.get('classroom_lecture_id')
    
    # Context Retrieval
    lecture = db.session.get(Lecture, lecture_id) if lecture_id else None
    context = lecture.transcript if lecture else "General academic knowledge."

    system_prompt = (
        "You are 'Professor StudAI', a helpful, witty, and brilliant academic mentor. "
        "Your tone is encouraging, clear, and professional. "
        f"Base your expertise on this context: {context[:6000]}"
    )

    try:
        # Update the model name as per your provider
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
        )
        answer = response.choices[0].message.content
        return jsonify({"answer": answer})
    except Exception as e:
        print(f"DEBUG ERROR: {str(e)}") # This will show up in your terminal
        return jsonify({"answer": "I'm currently reviewing some papers. Try again in a second!"}), 500