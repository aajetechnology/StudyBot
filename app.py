import os 
from flask import Flask, redirect, url_for
from app.models import db, User, Lecture, Quiz
from flask_login import LoginManager, current_user
from app.routes.auth import auth_bp, bcrypt
from app.routes.processor import processor_bp
from flask import redirect, url_for
from flask_login import current_user
from app.routes.quiz import quiz_bp


app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///studbot.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS']=False

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

db.init_app(app)
bcrypt.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/')
def index():
    if current_user.is_authenticated: 
        return redirect(url_for('processor.upload_lecture'))
    return redirect(url_for('auth.login'))
# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(processor_bp)
app.register_blueprint(quiz_bp)

