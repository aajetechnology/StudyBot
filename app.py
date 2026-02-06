import os 
from flask import Flask, redirect, url_for, jsonify, request
from app.models import db, User, Lecture, Quiz
from flask_login import LoginManager, current_user
from app.routes.auth import auth_bp, bcrypt
from app.routes.processor import processor_bp
from flask import redirect, url_for
from flask_login import current_user
from app.routes.quiz import quiz_bp
from utils.image_processor import analyze_note_image
from utils.lecture_processor import process_files, lecture_student


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


@app.route('/upload-note', methods=['POST'])
def upload_note():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400
    
    file = request.files['file']

    file_path = os.path.join("uploads", file.filename)
    file.save(file_path)
    explanation = analyze_note_image(file_path)
    os.remove(file_path)
    return jsonify({'explanation': explanation})


@app.route('/start-class', methods=['POST'])
def start_class():
    uploaded_files = request.files.getlist("lecture_files") # 'multiple' attribute in HTML
    saved_paths = []
    
    for file in uploaded_files:
        path = os.path.join("uploads", file.filename)
        file.save(path)
        saved_paths.append(path)
    
    # 1. Extract content from all files
    all_text = process_files(saved_paths)
    
    # 2. Get the AI Professor's lecture
    lecture_script = lecture_student(all_text)
    
    # 3. Clean up (Important for Render Free Tier!)
    for path in saved_paths:
        os.remove(path)
        
    return jsonify({"lecture": lecture_script})

@app.route('/')
def index():
    if current_user.is_authenticated: 
        return redirect(url_for('processor.upload_lecture'))
    return redirect(url_for('auth.login'))
# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(processor_bp)
app.register_blueprint(quiz_bp)

