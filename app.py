from flask import Flask, render_template, redirect, url_for, request, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from datetime import date, timedelta, datetime
import random
import string
import os
from forms import AttendanceForm, RegistrationForm, LoginForm, TermDateForm, ClassCodeForm, JoinClassForm, TeacherRegistrationForm, TeacherCodeForm, StudentCodeForm, StudentRegistrationForm, PasswordResetForm
import pandas as pd
import io
from werkzeug.security import generate_password_hash, check_password_hash
import re
from sqlalchemy import text

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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    class_code = db.Column(db.String(8), unique=True, nullable=True)  # Only for teachers

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    def generate_class_code(self):
        self.class_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        db.session.commit()

class AttendanceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    present = db.Column(db.Boolean, default=False)

class StudentIDTracker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    last_id = db.Column(db.Integer, nullable=False, default=0)

class Class(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(6), unique=True, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    students = db.relationship('User', secondary='class_students', backref='classes')

class ClassStudents(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('class.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

class TeacherCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(8), unique=True, nullable=False)
    description = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    used = db.Column(db.Boolean, default=False)

class TeacherStudent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)

class TermSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    number_of_terms = db.Column(db.Integer, default=4)
    term_length_weeks = db.Column(db.Integer, default=10)
    current_term = db.Column(db.Integer, default=1)
    year_start_date = db.Column(db.Date, nullable=True)

class Term(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    term_number = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    is_current = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __init__(self, **kwargs):
        super(Term, self).__init__(**kwargs)
        if self.is_current:
            # Set all other terms for this teacher to not current
            Term.query.filter_by(
                teacher_id=self.teacher_id, 
                is_current=True
            ).update({'is_current': False})

class StudentCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(8), unique=True, nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    description = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    used = db.Column(db.Boolean, default=False)

# User loader
@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except ValueError:
        # Handle special case for admin user
        if user_id == 'admin':
            admin_user = User.query.filter_by(email='admin').first()
            if admin_user:
                return admin_user
    return None

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

# Add this function to detect mobile devices
def is_mobile():
    user_agent = request.headers.get('User-Agent', '').lower()
    mobile_patterns = [
        'mobile', 'android', 'iphone', 'ipad', 'ipod', 
        'blackberry', 'windows phone'
    ]
    return any(pattern in user_agent for pattern in mobile_patterns)

# Update the context processor to make is_mobile available in all templates
@app.context_processor
def utility_processor():
    return {
        'is_mobile': is_mobile()
    }

# Routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    form = StudentRegistrationForm()
    
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data).first():
            flash('Email already registered. Please use a different email.', 'danger')
            return redirect(url_for('register'))

        # Find teacher by class code
        teacher = User.query.filter_by(
            class_code=form.registration_code.data,
            role='teacher'
        ).first()
        
        if not teacher:
            flash('Invalid class code.', 'danger')
            return redirect(url_for('register'))
            
        # Create student account
        student_id = generate_student_id()
        student = User(
            name=form.name.data,
            email=form.email.data,
            role='student',
            student_id=student_id
        )
        student.set_password(form.password.data)
        
        db.session.add(student)
        db.session.flush()  # This assigns the student.id
        
        # Assign student to the teacher
        teacher_student = TeacherStudent(
            teacher_id=teacher.id,
            student_id=student.id
        )
        db.session.add(teacher_student)
        
        db.session.commit()
        flash('Account created successfully! Please login.', 'success')
        return redirect(url_for('login'))
            
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            if user.role == 'teacher':
                flash('Please use teacher login page.', 'warning')
                return redirect(url_for('teacher_login'))
            login_user(user)
            flash('Login successful!', 'success')
            if user.role == 'admin':
                return redirect(url_for('admin_panel'))
            else:
                return redirect(url_for('student_dashboard'))
        else:
            flash('Login unsuccessful. Please check email and password.', 'danger')
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
    today = date.today()
    
    # Check if attendance is already marked
    already_marked = AttendanceRecord.query.filter_by(
        student_id=current_user.id, 
        date=today
    ).first() is not None
    
    # Get current term for the student
    teacher_assignment = TeacherStudent.query.filter_by(student_id=current_user.id).first()
    if teacher_assignment:
        current_term = Term.query.filter_by(
            teacher_id=teacher_assignment.teacher_id,
            is_current=True
        ).first()
        
        if current_term:
            # Get attendance records for current term only
            term_records = AttendanceRecord.query.filter_by(
                student_id=current_user.id
            ).filter(
                AttendanceRecord.date >= current_term.start_date,
                AttendanceRecord.date <= today
            ).all()
            
            # Calculate attendance based on school days up to today
            total_school_days = sum(1 for d in (current_term.start_date + timedelta(n) 
                                              for n in range((min(today, current_term.end_date) - current_term.start_date).days + 1)) 
                                  if d.weekday() < 5)
            
            present_days = sum(1 for record in term_records if record.present)
            monthly_percentage = (present_days / total_school_days * 100) if total_school_days > 0 else 0
        else:
            monthly_percentage = 0
    else:
        monthly_percentage = 0
    
    if form.validate_on_submit():
        if not already_marked:
            attendance_record = AttendanceRecord(
                student_id=current_user.id,
                date=today,
                present=True
            )
            db.session.add(attendance_record)
            db.session.commit()
            flash('Attendance marked successfully!', 'success')
            return redirect(url_for('mark_attendance'))
        else:
            flash('Attendance already marked for today.', 'warning')
    
    return render_template('mark_attendance.html', 
                         form=form,
                         today_date=today,
                         already_marked=already_marked,
                         monthly_percentage=monthly_percentage)

@app.route('/teacher_dashboard')
@login_required
def teacher_dashboard():
    if current_user.role != 'teacher':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    # Get current term
    current_term = Term.query.filter_by(
        teacher_id=current_user.id,
        is_current=True
    ).first()

    if not current_term:
        flash('Please configure your term settings first.', 'warning')
        return redirect(url_for('term_settings'))

    # Get all terms for the dropdown
    all_terms = Term.query.filter_by(
        teacher_id=current_user.id
    ).order_by(Term.term_number).all()

    # Calculate total school days up to today
    today = date.today()
    term_end = min(current_term.end_date, today)
    
    total_school_days = 0
    current_date = current_term.start_date
    while current_date <= term_end:
        if current_date.weekday() < 5:  # Skip weekends
            total_school_days += 1
        current_date += timedelta(days=1)

    # Calculate total term days (including future dates)
    total_term_days = 0
    current_date = current_term.start_date
    while current_date <= current_term.end_date:
        if current_date.weekday() < 5:
            total_term_days += 1
        current_date += timedelta(days=1)

    # Get students assigned to this teacher
    assigned_students = db.session.query(User).join(
        TeacherStudent, 
        TeacherStudent.student_id == User.id
    ).filter(
        TeacherStudent.teacher_id == current_user.id,
        User.role == 'student'
    ).all()

    student_data = []
    for student in assigned_students:
        attendance_records = AttendanceRecord.query.filter_by(
            student_id=student.id
        ).filter(
            AttendanceRecord.date.between(current_term.start_date, term_end)
        ).all()

        present_days = sum(1 for record in attendance_records if record.present)
        
        # Calculate percentage based on school days up to today
        attendance_percentage = (present_days / total_school_days * 100) if total_school_days > 0 else 0

        student_data.append({
            'name': student.name,
            'student_id': student.student_id,
            'email': student.email,
            'attendance_percentage': round(attendance_percentage, 2),
            'total_days': total_school_days,
            'present_days': present_days,
            'absent_days': total_school_days - present_days
        })

    return render_template('teacher_dashboard.html', 
                         student_data=student_data,
                         assigned_students=assigned_students,
                         current_term=current_term,
                         all_terms=all_terms,
                         total_school_days=total_school_days,
                         total_term_days=total_term_days,
                         today=today)

@app.route('/student_dashboard')
@login_required
def student_dashboard():
    if current_user.role != 'student':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    # Get the teacher assigned to this student
    teacher_assignment = TeacherStudent.query.filter_by(student_id=current_user.id).first()
    if not teacher_assignment:
        flash('You are not assigned to a teacher yet.', 'warning')
        return render_template('student_dashboard.html', 
                             has_data=False,
                             message='You are not assigned to a teacher yet.')

    # Get current term
    current_term = Term.query.filter_by(
        teacher_id=teacher_assignment.teacher_id,
        is_current=True
    ).first()
    
    if not current_term:
        flash('No active term configured by your teacher.', 'warning')
        return render_template('student_dashboard.html', 
                             has_data=False,
                             message='No active term configured by your teacher.')

    # Get attendance records for the current term
    attendance_records = AttendanceRecord.query.filter_by(
        student_id=current_user.id
    ).filter(
        AttendanceRecord.date.between(current_term.start_date, current_term.end_date)
    ).order_by(
        AttendanceRecord.date
    ).all()

    # Create a list of all school days in the term up to today
    today = date.today()
    term_end = min(current_term.end_date, today)  # Don't go beyond today
    
    all_dates = []
    attendance_data = []
    current_date = current_term.start_date
    
    while current_date <= term_end:
        if current_date.weekday() < 5:  # Monday to Friday
            all_dates.append(current_date)
            # Find if there's an attendance record for this date
            record = next((r for r in attendance_records if r.date == current_date), None)
            attendance_data.append(1 if record and record.present else 0)
        current_date += timedelta(days=1)

    # Format dates for display
    attendance_dates = [date.strftime('%Y-%m-%d') for date in all_dates]

    # Calculate term statistics (only for days up to today)
    total_days = len(all_dates)
    present_days = sum(attendance_data)
    attendance_percentage = (present_days / total_days * 100) if total_days > 0 else 0

    # Get all terms for the dropdown
    all_terms = Term.query.filter_by(
        teacher_id=teacher_assignment.teacher_id
    ).order_by(Term.term_number).all()

    # Calculate total school days in the full term (for display)
    total_term_days = 0
    current_date = current_term.start_date
    while current_date <= current_term.end_date:
        if current_date.weekday() < 5:
            total_term_days += 1
        current_date += timedelta(days=1)

    return render_template('student_dashboard.html',
                         has_data=True,
                         attendance_dates=attendance_dates,
                         attendance_data=attendance_data,
                         current_term=current_term,
                         all_terms=all_terms,
                         attendance_percentage=round(attendance_percentage, 1),
                         present_days=present_days,
                         total_days=total_days,
                         total_term_days=total_term_days,
                         today=today)

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
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))

    # Get user statistics
    total_users = User.query.count()
    student_count = User.query.filter_by(role='student').count()
    teacher_count = User.query.filter_by(role='teacher').count()

    # Get today's statistics
    today = datetime.now().date()
    new_users_today = User.query.filter(
        db.func.date(User.created_at) == today
    ).count()
    
    attendance_today = AttendanceRecord.query.filter(
        db.func.date(AttendanceRecord.date) == today
    ).count()

    # Get system statistics
    total_attendance = AttendanceRecord.query.count()
    
    # Calculate average attendance
    total_present = AttendanceRecord.query.filter_by(present=True).count()
    avg_attendance = round((total_present / total_attendance * 100) if total_attendance > 0 else 0, 1)

    # Get all teachers with their class codes and assigned students
    teachers = User.query.filter_by(role='teacher').all()
    teacher_data = []
    
    for teacher in teachers:
        # Get assigned students for this teacher
        assigned_students = db.session.query(User).join(
            TeacherStudent,
            TeacherStudent.student_id == User.id
        ).filter(
            TeacherStudent.teacher_id == teacher.id
        ).all()
        
        teacher_data.append({
            'teacher': teacher,
            'students': assigned_students,
            'student_count': len(assigned_students)
        })

    return render_template('admin_panel.html',
                         total_users=total_users,
                         student_count=student_count,
                         teacher_count=teacher_count,
                         new_users_today=new_users_today,
                         attendance_today=attendance_today,
                         total_attendance=total_attendance,
                         avg_attendance=avg_attendance,
                         teacher_data=teacher_data)

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
        if form.email.data == 'admin' and form.password.data == 'admin':
            user = User.query.filter_by(email='admin').first()
            if not user:
                # Create admin user if it doesn't exist
                user = User(name='Admin', email='admin', password='admin', role='admin')
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
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin_panel'))
        elif current_user.role == 'teacher':
            return redirect(url_for('teacher_dashboard'))
        else:  # student
            return redirect(url_for('student_dashboard'))
    return render_template('index.html')

@app.route('/admin/generate_class_code', methods=['GET', 'POST'])
@login_required
def generate_class_code():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    
    form = ClassCodeForm()
    if form.validate_on_submit():
        teacher = User.query.filter_by(email=form.teacher_email.data, role='teacher').first()
        if not teacher:
            flash('Teacher not found.', 'danger')
            return redirect(url_for('generate_class_code'))
        
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        new_class = Class(
            name=form.class_name.data,
            code=code,
            teacher_id=teacher.id
        )
        db.session.add(new_class)
        db.session.commit()
        flash(f'Class code generated: {code}', 'success')
        return redirect(url_for('admin_panel'))
    
    return render_template('generate_class_code.html', form=form)

@app.route('/join_class', methods=['GET', 'POST'])
@login_required
def join_class():
    if current_user.role != 'student':
        flash('Only students can join classes.', 'danger')
        return redirect(url_for('index'))
    
    form = JoinClassForm()
    if form.validate_on_submit():
        class_obj = Class.query.filter_by(code=form.class_code.data).first()
        if not class_obj:
            flash('Invalid class code.', 'danger')
            return redirect(url_for('join_class'))
        
        if current_user in class_obj.students:
            flash('You are already in this class.', 'warning')
            return redirect(url_for('student_dashboard'))
        
        class_obj.students.append(current_user)
        db.session.commit()
        flash('Successfully joined the class!', 'success')
        return redirect(url_for('student_dashboard'))
    
    return render_template('join_class.html', form=form)

@app.route('/download_report')
@login_required
def download_report():
    if current_user.role != 'student':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    
    # Get all attendance records for the student
    records = AttendanceRecord.query.filter_by(student_id=current_user.id).order_by(AttendanceRecord.date).all()
    
    # Create DataFrame
    data = {
        'Date': [record.date.strftime('%Y-%m-%d') for record in records],
        'Status': ['Present' if record.present else 'Absent' for record in records]
    }
    df = pd.DataFrame(data)
    
    # Calculate statistics
    total_days = len(records)
    present_days = sum(1 for record in records if record.present)
    attendance_rate = (present_days / total_days * 100) if total_days > 0 else 0
    
    # Add summary
    summary = pd.DataFrame({
        'Metric': ['Total Days', 'Present Days', 'Absent Days', 'Attendance Rate'],
        'Value': [total_days, present_days, total_days - present_days, f'{attendance_rate:.2f}%']
    })
    
    # Create Excel writer
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Attendance Records', index=False)
        summary.to_excel(writer, sheet_name='Summary', index=False)
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'attendance_report_{current_user.name}.xlsx'
    )

@app.route('/teacher_login', methods=['GET', 'POST'])
def teacher_login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data, role='teacher').first()
        if user and user.check_password(form.password.data):
            login_user(user)
            flash('Login successful!', 'success')
            return redirect(url_for('teacher_dashboard'))
        else:
            flash('Invalid teacher credentials.', 'danger')
    return render_template('teacher_login.html', form=form)

@app.route('/teacher_register', methods=['GET', 'POST'])
def teacher_register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    form = TeacherRegistrationForm()
    if form.validate_on_submit():
        # Create new teacher account
        teacher = User(
            name=form.name.data,
            email=form.email.data,
            role='teacher'
        )
        teacher.set_password(form.password.data)
        teacher.generate_class_code()  # Generate initial class code
        
        db.session.add(teacher)
        db.session.commit()
        
        flash('Teacher account created successfully! Please login.', 'success')
        return redirect(url_for('teacher_login'))
        
    return render_template('teacher_register.html', form=form)

@app.route('/admin/view_teacher_codes')
@login_required
def view_teacher_codes():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
        
    codes = TeacherCode.query.order_by(TeacherCode.created_at.desc()).all()
    return render_template('view_teacher_codes.html', codes=codes)

def verify_teacher_code(code):
    teacher_code = TeacherCode.query.filter_by(
        code=code, 
        used=False
    ).first()
    if teacher_code:
        teacher_code.used = True
        db.session.commit()
        return True
    return False

@app.route('/admin/generate_teacher_code', methods=['GET', 'POST'])
@login_required
def generate_teacher_code():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    
    form = TeacherCodeForm()
    if form.validate_on_submit():
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        teacher_code = TeacherCode(
            code=code,
            description=form.description.data
        )
        db.session.add(teacher_code)
        db.session.commit()
        flash(f'Teacher registration code generated: {code}', 'success')
        return redirect(url_for('admin_panel'))
    
    return render_template('generate_teacher_code.html', form=form)

@app.route('/admin/assign_teacher', methods=['GET', 'POST'])
@login_required
def assign_teacher():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    
    teachers = User.query.filter_by(role='teacher').all()
    students = User.query.filter_by(role='student').all()
    
    if request.method == 'POST':
        teacher_id = request.form.get('teacher_id')
        student_ids = request.form.getlist('student_ids')
        
        if not teacher_id or not student_ids:
            flash('Please select both teacher and students.', 'danger')
            return redirect(url_for('assign_teacher'))
            
        # Remove existing assignments for selected students
        TeacherStudent.query.filter(
            TeacherStudent.student_id.in_(student_ids)
        ).delete(synchronize_session=False)
        
        # Create new assignments
        for student_id in student_ids:
            assignment = TeacherStudent(
                teacher_id=teacher_id,
                student_id=student_id
            )
            db.session.add(assignment)
            
        db.session.commit()
        flash('Teacher-student assignments updated successfully!', 'success')
        return redirect(url_for('admin_panel'))
        
    # Get current assignments
    assignments = TeacherStudent.query.all()
    student_assignments = {ts.student_id: ts.teacher_id for ts in assignments}
    
    return render_template('assign_teacher.html',
                         teachers=teachers,
                         students=students,
                         current_assignments=student_assignments)

@app.route('/term_settings', methods=['GET', 'POST'])
@login_required
def term_settings():
    if current_user.role != 'teacher':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    
    # Handle term editing
    if request.method == 'POST':
        # Get form data
        term_number = int(request.form.get('term_number'))
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d').date()
        is_current = bool(request.form.get('is_current'))

        # Validate dates
        if start_date >= end_date:
            flash('End date must be after start date.', 'danger')
            return redirect(url_for('term_settings'))

        # Check for overlapping dates with other terms
        overlapping_term = Term.query.filter(
            Term.teacher_id == current_user.id,
            Term.id != request.form.get('term_id', None),  # Exclude current term when editing
            Term.start_date <= end_date,
            Term.end_date >= start_date
        ).first()

        if overlapping_term:
            flash('Term dates overlap with an existing term.', 'danger')
            return redirect(url_for('term_settings'))

        if 'term_id' in request.form:  # Editing existing term
            term = Term.query.get_or_404(request.form['term_id'])
            if term.teacher_id != current_user.id:
                flash('Access denied.', 'danger')
                return redirect(url_for('term_settings'))
                
            term.term_number = term_number
            term.start_date = start_date
            term.end_date = end_date
            term.is_current = is_current
            flash('Term updated successfully!', 'success')
        else:  # Creating new term
            term = Term(
                teacher_id=current_user.id,
                term_number=term_number,
                start_date=start_date,
                end_date=end_date,
                is_current=is_current
            )
            db.session.add(term)
            flash('New term added successfully!', 'success')

        db.session.commit()
        return redirect(url_for('term_settings'))
    
    # GET request - display terms
    terms = Term.query.filter_by(teacher_id=current_user.id).order_by(Term.term_number).all()
    return render_template('term_settings.html', terms=terms)

@app.route('/teacher/generate_student_code', methods=['GET', 'POST'])
@login_required
def generate_student_code():
    if current_user.role != 'teacher':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    
    form = StudentCodeForm()  # You'll need to create this form
    if form.validate_on_submit():
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        student_code = StudentCode(
            code=code,
            teacher_id=current_user.id,
            description=form.description.data
        )
        db.session.add(student_code)
        db.session.commit()
        flash(f'Student registration code generated: {code}', 'success')
        return redirect(url_for('teacher_dashboard'))
    
    return render_template('generate_student_code.html', form=form)

@app.route('/teacher/view_student_codes')
@login_required
def view_student_codes():
    if current_user.role != 'teacher':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
        
    codes = StudentCode.query.filter_by(teacher_id=current_user.id).order_by(StudentCode.created_at.desc()).all()
    return render_template('view_student_codes.html', codes=codes)

@app.route('/teacher/regenerate_class_code', methods=['POST'])
@login_required
def regenerate_class_code():
    if current_user.role != 'teacher':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    
    current_user.generate_class_code()
    flash('Class code regenerated successfully!', 'success')
    return redirect(url_for('term_settings'))

@app.route('/admin/reset_password/<int:user_id>', methods=['GET', 'POST'])
@login_required
def reset_password(user_id):
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('index'))
    
    user = User.query.get_or_404(user_id)
    form = PasswordResetForm()
    
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash(f'Password reset successful for {user.name}.', 'success')
        return redirect(url_for('admin_panel'))
    
    return render_template('reset_password.html', form=form, user=user)

# Initialize database
def setup_database():
    with app.app_context():
        # Create tables and add class_code column
        db.create_all()
        
        # Create admin user if it doesn't exist
        admin_user = User.query.filter_by(email='admin').first()
        if not admin_user:
            admin_user = User(
                name='Administrator',
                email='admin',
                role='admin'
            )
            admin_user.set_password('adiyogi1')  # Set the admin password
            db.session.add(admin_user)
            db.session.commit()

        # Check if we need to add the class_code column
        inspector = db.inspect(db.engine)
        if 'class_code' not in [c['name'] for c in inspector.get_columns('user')]:
            # For SQLite, we need to:
            # 1. Create a new table
            # 2. Copy the data
            # 3. Drop the old table
            # 4. Rename the new table
            with db.engine.connect() as conn:
                conn.execute(text('''
                    CREATE TABLE user_new (
                        id INTEGER PRIMARY KEY,
                        name VARCHAR(100) NOT NULL,
                        email VARCHAR(120) UNIQUE NOT NULL,
                        password VARCHAR(60) NOT NULL,
                        role VARCHAR(10) NOT NULL,
                        student_id VARCHAR(10) UNIQUE,
                        created_at DATETIME,
                        class_code VARCHAR(8) UNIQUE
                    )
                '''))
                
                # Copy existing data
                conn.execute(text('''
                    INSERT INTO user_new (id, name, email, password, role, student_id, created_at)
                    SELECT id, name, email, password, role, student_id, created_at
                    FROM user
                '''))
                
                # Drop old table and rename new one
                conn.execute(text('DROP TABLE user'))
                conn.execute(text('ALTER TABLE user_new RENAME TO user'))
                conn.commit()

        # Initialize StudentIDTracker if needed
        if not StudentIDTracker.query.first():
            db.session.add(StudentIDTracker(last_id=0))
            db.session.commit()

if __name__ == '__main__':
    setup_database()
    app.run(debug=True, port=5002,host='0.0.0.0') 