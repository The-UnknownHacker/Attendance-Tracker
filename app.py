from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from datetime import date, timedelta
import random
import string
import os
from forms import AttendanceForm, RegistrationForm, LoginForm, TermDateForm

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    role = db.Column(db.String(10), nullable=False, default='student')  # 'student' or 'teacher'
    student_id = db.Column(db.String(10), unique=True, nullable=True)  # Only for students

class AttendanceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    present = db.Column(db.Boolean, default=False)

class StudentIDTracker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    last_id = db.Column(db.Integer, nullable=False, default=0)

# User loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Utility function
def generate_student_id():
    tracker = StudentIDTracker.query.first()
    if not tracker:
        tracker = StudentIDTracker(last_id=0)
        db.session.add(tracker)
        db.session.commit()

    if tracker.last_id >= 1000:
        raise ValueError("Maximum student ID reached")

    tracker.last_id += 1
    db.session.commit()

    return f"{tracker.last_id:04d}"

def calculate_attendance_percentage_for_term(attendance_records, start_date, end_date):
    term_records = [record for record in attendance_records if start_date <= record.date <= end_date]
    total_classes = len(term_records)
    attended_classes = sum(record.present for record in term_records)
    return (attended_classes / total_classes * 100) if total_classes > 0 else 0

# Routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            name=form.name.data,
            email=form.email.data,
            password=form.password.data,
            student_id=generate_student_id(),
            role='student'  # Default to student role
        )
        db.session.add(user)
        db.session.commit()
        flash('Sign Up Successfull. Please Login to continue.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.password == form.password.data:
            login_user(user)
            flash('Login successful!', 'success')
            if user.role == 'admin':
                return redirect(url_for('admin_panel'))
            elif user.role == 'teacher':
                return redirect(url_for('teacher_dashboard'))
            else:
                return redirect(url_for('student_dashboard'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/mark_attendance', methods=['GET', 'POST'])
@login_required
def mark_attendance():
    form = AttendanceForm()
    if form.validate_on_submit():
        today = date.today()
        existing_record = AttendanceRecord.query.filter_by(student_id=current_user.id, date=today).first()
        
        if existing_record:
            flash('Attendance for today has already been marked.', 'info')
        else:
            attendance_record = AttendanceRecord(
                student_id=current_user.id,
                date=today,
                present=True
            )
            db.session.add(attendance_record)
            db.session.commit()
            flash('Attendance marked successfully!', 'success')
        
        return redirect(url_for('student_dashboard'))
    
    return render_template('mark_attendance.html', form=form)

@app.route('/teacher_dashboard', methods=['GET', 'POST'])
@login_required
def teacher_dashboard():
    if current_user.role not in ['teacher', 'admin']:
        flash('Access denied. Only teachers and admins can access this page.', 'danger')
        return redirect(url_for('index'))

    form = TermDateForm()
    student_data = []

    if form.validate_on_submit():
        start_date = form.start_date.data
        end_date = form.end_date.data

        students = User.query.filter_by(role='student').all()
        for student in students:
            attendance_records = AttendanceRecord.query.filter(
                AttendanceRecord.student_id == student.id,
                AttendanceRecord.date >= start_date,
                AttendanceRecord.date <= end_date
            ).all()
            attendance_percentage = calculate_attendance_percentage_for_term(attendance_records, start_date, end_date)
            student_data.append({
                'name': student.name,
                'student_id': student.student_id,
                'email': student.email,
                'attendance_percentage': attendance_percentage
            })

    return render_template('teacher_dashboard.html', form=form, student_data=student_data)

@app.route('/student_dashboard')
@login_required
def student_dashboard():
    attendance_records = AttendanceRecord.query.filter_by(student_id=current_user.id).all()
    attendance_dates = [record.date.strftime('%Y-%m-%d') for record in attendance_records]
    attendance_data = [1 if record.present else 0 for record in attendance_records]
    return render_template('student_dashboard.html', attendance_dates=attendance_dates, attendance_data=attendance_data)

@app.route('/student/<student_id>')
@login_required
def student_detail(student_id):
    student = User.query.filter_by(student_id=student_id).first_or_404()
    attendance_records = AttendanceRecord.query.filter_by(student_id=student.id).all()
    return render_template('student_detail.html', student=student, attendance_records=attendance_records)

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin_panel():
    if current_user.role != 'admin':
        flash('You are not allowed to access the admin panel.', 'danger')
        return redirect(url_for('login'))

    students = User.query.filter_by(role='student').all()
    teachers = User.query.filter_by(role='teacher').all()
    return render_template('admin_panel.html', students=students, teachers=teachers)

@app.route('/admin/add_user', methods=['GET', 'POST'])
@login_required
def add_user():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    form = RegistrationForm()
    if form.validate_on_submit():
        role = request.form.get('role')
        user = User(
            name=form.name.data,
            email=form.email.data,
            password=form.password.data,
            role=role
        )
        if role == 'student':
            user.student_id = generate_student_id()
        
        db.session.add(user)
        db.session.commit()
        flash('User added successfully!', 'success')
        return redirect(url_for('admin_panel'))
    return render_template('add_user.html', form=form)

@app.route('/admin/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    if current_user.email != 'admin' or current_user.password != 'adiyogi1':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    user = User.query.get_or_404(user_id)
    form = RegistrationForm(obj=user)
    if form.validate_on_submit():
        user.name = form.name.data
        user.email = form.email.data
        user.password = form.password.data
        user.role = request.form.get('role')
        db.session.commit()
        flash('User updated successfully!', 'success')
        return redirect(url_for('admin_panel'))
    return render_template('edit_user.html', form=form, user=user)

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if current_user.email != 'admin' or current_user.password != 'adiyogi1':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash('User deleted successfully!', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    form = LoginForm()
    if form.validate_on_submit():
        if form.email.data == 'admin' and form.password.data == 'adiyogi1':
            user = User.query.filter_by(email='admin').first()
            if not user:
                # Create admin user if it doesn't exist
                user = User(name='Admin', email='admin', password='adiyogi1', role='admin')
                db.session.add(user)
                db.session.commit()
            login_user(user)
            flash('Admin login successful!', 'success')
            return redirect(url_for('admin_panel'))
        else:
            flash('Invalid admin credentials.', 'danger')
    return render_template('admin_login.html', form=form)

@app.route('/')
def index():
    return render_template('index.html')

# Initialize database
def setup_database():
    with app.app_context():
        db.create_all()
        if not StudentIDTracker.query.first():
            db.session.add(StudentIDTracker(last_id=0))
            db.session.commit()

if __name__ == '__main__':
    setup_database()
    app.run(debug=True, port=5001,host='0.0.0.0') 