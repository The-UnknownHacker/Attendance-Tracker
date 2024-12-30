from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, DateField
from wtforms.validators import DataRequired, EqualTo, Email, Length, Optional

class RegistrationForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Sign Up')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class AttendanceForm(FlaskForm):
    submit = SubmitField('Mark Attendance for Today')

class TermDateForm(FlaskForm):
    start_date = DateField('Term Start Date', format='%Y-%m-%d', validators=[DataRequired()])
    end_date = DateField('Term End Date', format='%Y-%m-%d', validators=[DataRequired()])
    submit = SubmitField('Calculate Attendance')

class ClassCodeForm(FlaskForm):
    class_name = StringField('Class Name', validators=[DataRequired()])
    teacher_email = StringField('Teacher Email', validators=[DataRequired()])
    submit = SubmitField('Generate Code')

class JoinClassForm(FlaskForm):
    class_code = StringField('Class Code', validators=[DataRequired()])
    submit = SubmitField('Join Class')

class TeacherRegistrationForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password', 
        validators=[DataRequired(), EqualTo('password')])
    teacher_code = StringField('Teacher Registration Code', validators=[DataRequired()])
    submit = SubmitField('Register')

class TeacherCodeForm(FlaskForm):
    description = StringField('Description', validators=[DataRequired()])
    submit = SubmitField('Generate Code')

class StudentRegistrationForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    registration_code = StringField('Registration Code', validators=[DataRequired()])
    submit = SubmitField('Register')

class StudentCodeForm(FlaskForm):
    description = StringField('Description (optional)', validators=[Optional(), Length(max=200)])
    submit = SubmitField('Generate Code')

class PasswordResetForm(FlaskForm):
    password = PasswordField('New Password', validators=[
        DataRequired(),
        Length(min=6, message='Password must be at least 6 characters long')
    ])
    submit = SubmitField('Reset Password')
  