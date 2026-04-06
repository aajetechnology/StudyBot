from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import login_user, logout_user, current_user
from flask_bcrypt import Bcrypt
from app.models import db, User

import hmac
import hashlib
import json
import urllib.parse
import os

auth_bp = Blueprint('auth', __name__)
bcrypt = Bcrypt()

@auth_bp.route('/register', methods=['GET', 'POST'])

def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email =request.form.get('email')
        password = request.form.get('password')

        user_exists = User.query.filter_by(email=email).first()
        if user_exists:
            flash('Email alreadyregistered . ', 'danger')
            return redirect(url_for('auth.register'))
        
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        is_first_user = User.query.count() == 0

        new_user = User(username=username, email=email, password=hashed_password, is_admin=is_first_user)
        db.session.add(new_user)
        db.session.commit()
        
        flash('Account created! You can now log in.', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template('register.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('processor.dashboard'))
        else:
            flash('Login Unsuccessful. Check email and password', 'danger')
            
    return render_template('login.html')


@auth_bp.route('/telegram-login', methods=['POST'])
def telegram_login():
    data = request.json
    init_data = data.get('initData')
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")

    if not verify_telegram_data(init_data, bot_token):
        return jsonify({'success': False, "message": "Invalid Security Hash"}), 403
    
    params = dict(urllib.parse.parse_qsl(init_data))
    user_data = json.loads(params.get('user'))
    telegram_id = user_data.get('id')

    # Check if user exists by Telegram ID
    user = User.query.filter_by(telegram_id=telegram_id).first()

    if not user:
        # Create a new user automatically
        user = User(
            username=user_data.get('username') or f"user_{telegram_id}",
            telegram_id=telegram_id,
            email=f"{telegram_id}@t.me", # Placeholder email
            is_premium=False
        )
        db.session.add(user)
        db.session.commit()

    # Log them in and tell the frontend where to go
    login_user(user, remember=True)
    return jsonify({
        'success': True, 
        "redirect": url_for('processor.dashboard')
    })

def verify_telegram_data(init_data, bot_token):
    vals = dict(urllib.parse.parse_qsl(init_data))
    hash_val = vals.pop('hash', None)
    data_check_string = "\n".join([f"{k}={v}" for k, v in sorted(vals.items())])
    secret_key = hmac.new("WebAppData".encode(), bot_token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return h == hash_val
@auth_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('auth.login'))




