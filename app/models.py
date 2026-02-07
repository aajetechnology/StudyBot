from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime


db =  SQLAlchemy()


class User(db.Model, UserMixin):
    __tablename__='users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)



    is_admin = db.Column(db.Boolean, default=False)

    lectures = db.relationship('Lecture', backref='owner', lazy=True)

    def __repr__(self):
        return f"<User {self.username}>"
    

class Lecture(db.Model):
        __tablename__ = 'lectures'
        id = db.Column(db.Integer, primary_key=True)
        title = db.Column(db.String(255), nullable=False)
        timestamp = db.Column(db.DateTime, nullable=False)

        transcript = db.Column(db.Text)
        summary = db.Column(db.Text, nullable=True)

        original_filename = db.Column(db.String(100))
        output_format = db.Column(db.String(10))

        user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

        def __repr__(self):
            return f'<Lecture {self.title}>'
        

class Quiz(db.Model):
    __tablename__ = 'quizzes'
    id = db.Column(db.Integer, primary_key=True)
    lecture_id = db.Column(db.Integer, db.ForeignKey('lectures.id'), nullable=True)
    title = db.Column(db.String(200))
    questions_json = db.Column(db.Text)  
    user_answers = db.Column(db.Text)    
    score = db.Column(db.Integer)
    total_questions = db.Column(db.Integer)
    feedback = db.Column(db.Text)        
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    lecture_id= db.Column(db.Integer, db.ForeignKey('lectures.id'), nullable=False)
    lecture = db.relationship('Lecture', backref='quizzes')




class ClassSession(db.Model):
    __tablename__ = 'class_session'
    id = db.Column(db.Integer, primary_key=True)
    
    # FIX: Point to 'users.id' (Matches your User table)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # FIX: Point to 'lectures.id' (Matches your Lecture table)
    lecture_id = db.Column(db.Integer, db.ForeignKey('lectures.id'), nullable=False)
    
    current_module_index = db.Column(db.Integer, default=0)
    modules_json = db.Column(db.Text) 
    is_active = db.Column(db.Boolean, default=True)

    # Relationships
    lecture = db.relationship('Lecture', backref='class_sessions')
    user = db.relationship('User', backref='class_sessions')