import bleach
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, BooleanField, SelectField, SelectMultipleField, TextAreaField, IntegerField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, NumberRange
from models import User

def sanitize_html(text):
    """Sanitizes user input string using bleach to prevent XSS attacks."""
    if not text:
        return ""
    # Strip all HTML tags for plain text user inputs
    return bleach.clean(text, tags=[], strip=True)

class RegistrationForm(FlaskForm):
    name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email Address', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6, max=50)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match')])
    submit = SubmitField('Create Account')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data.strip().lower()).first()
        if user:
            raise ValidationError('Email address is already registered. Please login.')


class LoginForm(FlaskForm):
    email = StringField('Email Address', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Sign In')


class ProfileForm(FlaskForm):
    name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email Address', validators=[DataRequired(), Email(), Length(max=120)])
    profile_photo = FileField('Update Profile Photo', validators=[FileAllowed(['jpg', 'jpeg', 'png', 'webp', 'gif'], 'Images only!')])
    submit = SubmitField('Save Profile')


class RecommendationForm(FlaskForm):
    budget_level = SelectField('Budget Tier', choices=[
        ('Any', 'Any Budget Tier'),
        ('Budget', 'Budget Friendly ($)'),
        ('Moderate', 'Moderate ($$)'),
        ('Luxury', 'Luxury ($$$)')
    ], default='Any')

    category = SelectField('Travel Category', choices=[
        ('Any', 'All Categories'),
        ('Beach', 'Beach & Coastal'),
        ('Mountain', 'Mountain & Snow'),
        ('Heritage', 'Heritage & Architecture'),
        ('Nature', 'Nature & Eco-Tourism'),
        ('City', 'City & Shopping'),
        ('Adventure', 'Adventure & Sports'),
        ('Culture', 'Culture & Spiritual'),
        ('Island', 'Tropical Island'),
        ('Desert', 'Desert Safari'),
        ('Wildlife', 'Wildlife & Jungle')
    ], default='Any')

    interests = SelectMultipleField('Interests & Vibe (Hold Ctrl to select multiple)', choices=[
        ('food', 'Gourmet & Street Food'),
        ('nightlife', 'Nightlife & Bars'),
        ('trekking', 'Trekking & Hiking'),
        ('spiritual', 'Spiritual & Temples'),
        ('photography', 'Photography & Scenery'),
        ('water sports', 'Scuba & Water Sports'),
        ('shopping', 'Local Bazaars & Shopping'),
        ('history', 'Ancient History & Museums'),
        ('relaxed', 'Relaxation & Spa'),
        ('snow', 'Snow & Skiing')
    ])

    preferred_state = StringField('Preferred Region / State / Country (Optional)', validators=[Length(max=100)])
    submit = SubmitField('Find Best Matches')


class PostForm(FlaskForm):
    caption = TextAreaField('Caption', validators=[DataRequired(), Length(min=2, max=1000)])
    location_name = StringField('Location Tag (e.g. Goa, Paris, Taj Mahal)', validators=[DataRequired(), Length(max=150)])
    image = FileField('Upload Photo', validators=[FileAllowed(['jpg', 'jpeg', 'png', 'webp', 'gif'], 'Images only!')])
    submit = SubmitField('Publish Post')


class CommentForm(FlaskForm):
    comment_text = TextAreaField('Add Comment', validators=[DataRequired(), Length(min=1, max=500)])
    submit = SubmitField('Post Comment')


class ItineraryForm(FlaskForm):
    destination = StringField('Destination Name', validators=[DataRequired(), Length(max=120)])
    days = IntegerField('Number of Days (1 - 7)', validators=[DataRequired(), NumberRange(min=1, max=7)], default=3)
    budget = SelectField('Budget Level', choices=[
        ('Budget', 'Budget ($)'),
        ('Moderate', 'Moderate ($$)'),
        ('Luxury', 'Luxury ($$$)')
    ], default='Moderate')
    submit = SubmitField('Generate AI Itinerary')
