from flask_login import login_required, current_user

@admin_bp.route('/admin')
@login_required
def admin_panel():
    if not current_user.is_admin:
        flash('Unauthorized Access!', 'danger')
        return redirect(url_for('main.dashboard'))
        
    users = User.query.all()
    return render_template('admin.html', users=users)