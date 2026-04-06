import os
from flask import Flask, redirect, url_for
from flask_login import LoginManager, current_user
from flask_migrate import Migrate
from config import Config
from app.models import db, User
from app.routes.library import library_bp
from app.routes.classroom import classroom_bp


# Initialize extensions globally
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Ensure Upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Init Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # Register Blueprints
    from app.routes.auth import auth_bp
    from app.routes.processor import processor_bp
    from app.routes.quiz import quiz_bp
    from app.routes.chatfroff import chatproff_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(processor_bp)
    app.register_blueprint(quiz_bp, url_prefix='/quiz')
    app.register_blueprint(library_bp)
    app.register_blueprint(classroom_bp)
    app.register_blueprint(chatproff_bp)

    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('processor.dashboard')) # Updated to dashboard
        return redirect(url_for('auth.login'))

    return app

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))