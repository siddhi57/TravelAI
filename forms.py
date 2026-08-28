import bleach
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, SubmitField, BooleanField, SelectField, SelectMultipleField, TextAreaField, IntegerField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, NumberRange
from flask_login import current_user
from models import User

def sanitize_html(text):
    """Sanitizes user input string using bleach to prevent XSS attacks."""
    if not text:
        return ""
    # Strip all HTML tags for plain text user inputs
    return bleach.clean(text, tags=[], strip=True)


class UniqueEmailValidator:
    """Reusable validator for email uniqueness across Registration and Profile forms."""
    def __init__(self, message='Email address is already registered. Please use another email.'):
        self.message = message

    def __call__(self, form, field):
        email_clean = field.data.strip().lower() if field.data else ""
        if not email_clean:
            return
            
        if current_user and current_user.is_authenticated and current_user.email.lower() == email_clean:
            return

        user = User.query.filter_by(email=email_clean).first()
        if user:
            raise ValidationError(self.message)


class PasswordComplexityValidator:
    """Ensures password meets security criteria (at least 8 chars)."""
    def __init__(self, min_length=8):
        self.min_length = min_length

    def __call__(self, form, field):
        pwd = field.data or ""
        if len(pwd) < self.min_length:
            raise ValidationError(f"Password must be at least {self.min_length} characters long.")


class RegistrationForm(FlaskForm):
    name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email Address', validators=[DataRequired(), Email(), Length(max=120), UniqueEmailValidator()])
    password = PasswordField('Password', validators=[DataRequired(), PasswordComplexityValidator(8), Length(max=50)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match')])
    submit = SubmitField('Create Account')


class LoginForm(FlaskForm):
    email = StringField('Email Address', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Remember Me')
    submit = SubmitField('Sign In')


class ProfileForm(FlaskForm):
    name = StringField('Full Name', validators=[DataRequired(), Length(min=2, max=100)])
    email = StringField('Email Address', validators=[DataRequired(), Email(), Length(max=120), UniqueEmailValidator()])
    profile_photo = FileField('Update Profile Photo', validators=[FileAllowed(['jpg', 'jpeg', 'png', 'webp', 'gif'], 'Images only!')])
    submit = SubmitField('Save Profile')


class DestinationForm(FlaskForm):
    name = StringField('Destination Name', validators=[DataRequired(), Length(min=2, max=120)])
    state = StringField('State / Region / Country', validators=[DataRequired(), Length(min=2, max=100)])
    category = SelectField('Category', choices=[
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
    ], validators=[DataRequired()])
    budget_level = SelectField('Budget Level', choices=[
        ('Budget', 'Budget ($)'),
        ('Moderate', 'Moderate ($$)'),
        ('Luxury', 'Luxury ($$$)')
    ], validators=[DataRequired()])
    description = TextAreaField('Description', validators=[DataRequired(), Length(min=10, max=1000)])
    tags = StringField('Tags (space-separated)', validators=[Length(max=255)])
    submit = SubmitField('Save Destination')


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
