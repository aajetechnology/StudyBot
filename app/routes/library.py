from datetime import datetime
from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models import db, Lecture,  Quiz




library_bp = Blueprint("library", __name__)

@library_bp.route("/library")
@login_required
def library_index():
    lectures = Lecture.query.filter_by(user_id=current_user.id).order_by(Lecture.timestamp.desc()).all()
    quizzes = Quiz.query.filter_by(user_id=current_user.id).order_by(Quiz.timestamp.desc()).all()

    total_quizzes =  len(quizzes)
    avg_score = 0
    if total_quizzes >0:
        total_points = sum(q.score for q in quizzes)
        total_possible = sum(q.total_questions for q in quizzes)
        avg_score= round((total_points / total_possible) *100) if total_possible > 0 else 0

    return render_template("library.html", lectures=lectures, quizzes=quizzes, total_quizzes=total_quizzes, 
                           avg_score=round(avg_score))

