from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, DateField
from wtforms.validators import DataRequired, EqualTo

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