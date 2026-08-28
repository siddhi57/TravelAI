import os
import math
from datetime import datetime, timedelta
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename

from config import Config
from models import db, User, Destination, HotelsCache, Post, Like, Comment
from forms import RegistrationForm, LoginForm, ProfileForm, RecommendationForm, PostForm, CommentForm, ItineraryForm, sanitize_html
from ml.recommender import recommender_engine
from api.weather import get_current_weather, get_weather_forecast
from api.geoapify import geocode_location, get_nearby_hotels, get_nearby_attractions

app = Flask(__name__)
app.config.from_object(Config)

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize extensions
db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# Initialize database and populate dataset if empty
def init_db():
    with app.app_context():
        db.create_all()
        # Seed destinations if table is empty
        if Destination.query.count() == 0:
            csv_path = os.path.join(app.root_path, 'datasets', 'destinations.csv')
            if os.path.exists(csv_path):
                import pandas as pd
                df = pd.read_csv(csv_path)
                df.fillna('', inplace=True)
                for _, row in df.iterrows():
                    dest = Destination(
                        name=row['name'],
                        state=row['state'],
                        category=row['category'],
                        budget_level=row['budget_level'],
                        description=row['description'],
                        tags=row['tags']
                    )
                    db.session.add(dest)
                db.session.commit()
                print("Database initialized & destinations dataset seeded successfully!")

init_db()

# Allowed image extension checker
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


# --- ROUTES ---

@app.route('/')
def index():
    featured_destinations = Destination.query.limit(6).all()
    recent_posts = Post.query.order_by(Post.created_at.desc()).limit(3).all()
    return render_template('index.html', destinations=featured_destinations, posts=recent_posts)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            name=sanitize_html(form.name.data),
            email=form.email.data.strip().lower()
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Account created successfully! You can now log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.strip().lower()).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            flash(f'Welcome back, {user.name}!', 'success')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Invalid email or password. Please try again.', 'danger')
    return render_template('login.html', form=form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        # Check email uniqueness if changed
        if form.email.data.lower() != current_user.email.lower():
            existing = User.query.filter_by(email=form.email.data.lower()).first()
            if existing:
                flash('That email is already in use by another account.', 'danger')
                return render_template('profile.html', form=form)
        
        current_user.name = sanitize_html(form.name.data)
        current_user.email = form.email.data.strip().lower()
        
        if form.profile_photo.data and allowed_file(form.profile_photo.data.filename):
            file = form.profile_photo.data
            filename = secure_filename(f"user_{current_user.id}_{int(datetime.utcnow().timestamp())}_{file.filename}")
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            current_user.profile_photo = filename

        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))
        
    return render_template('profile.html', form=form)


@app.route('/recommendations', methods=['GET', 'POST'])
def recommendations():
    form = RecommendationForm()
    results = None
    
    if request.method == 'POST' and form.validate_on_submit():
        budget = form.budget_level.data
        category = form.category.data
        interests = form.interests.data
        preferred_state = form.preferred_state.data
        
        try:
            results = recommender_engine.recommend(
                budget_level=budget,
                category=category,
                interests=interests,
                preferred_state=preferred_state,
                top_n=5
            )
        except Exception as e:
            flash(f"Error computing recommendations: {str(e)}", "danger")
            results = []
    else:
        # Default recommendations for first view
        results = recommender_engine.recommend(top_n=5)
        
    return render_template('recommendations.html', form=form, results=results)


@app.route('/hotels')
def hotels():
    destination_name = request.args.get('destination', 'Goa').strip()
    budget_filter = request.args.get('budget', 'Any').strip()
    
    dest_obj = Destination.query.filter(Destination.name.ilike(destination_name)).first()
    dest_id = dest_obj.id if dest_obj else None
    
    # Check cache table for recent hotels (within 24 hours)
    cached_hotels = []
    if dest_id:
        cached_query = HotelsCache.query.filter_by(destination_id=dest_id).filter(
            HotelsCache.fetched_at >= datetime.utcnow() - timedelta(hours=24)
        ).all()
        if cached_query:
            cached_hotels = [h.to_dict() for h in cached_query]

    if not cached_hotels:
        try:
            fetched = get_nearby_hotels(destination_name, budget_tier=budget_filter, limit=10)
            cached_hotels = fetched
            
            # Save to database cache table if valid destination object exists
            if dest_id and fetched:
                # Clear old cache for this destination
                HotelsCache.query.filter_by(destination_id=dest_id).delete()
                for h in fetched:
                    cache_item = HotelsCache(
                        destination_id=dest_id,
                        hotel_name=h.get('hotel_name'),
                        address=h.get('address'),
                        rating=h.get('rating'),
                        price_tier=h.get('price_tier'),
                        lat=h.get('lat'),
                        lng=h.get('lng'),
                        fetched_at=datetime.utcnow()
                    )
                    db.session.add(cache_item)
                db.session.commit()
        except Exception as e:
            flash(f"Could not retrieve hotel data: {str(e)}", "warning")
            cached_hotels = []

    # Sort & filter
    if budget_filter and budget_filter != 'Any':
        filtered = [h for h in cached_hotels if str(h.get('price_tier')).lower() == budget_filter.lower()]
        if filtered:
            cached_hotels = filtered
            
    # Sort by rating descending
    cached_hotels.sort(key=lambda x: x.get('rating', 0), reverse=True)
    
    coords = geocode_location(destination_name)
    
    return render_template('hotels.html', 
                           destination=destination_name, 
                           hotels=cached_hotels, 
                           coords=coords,
                           budget_filter=budget_filter)


@app.route('/weather')
def weather():
    destination_name = request.args.get('destination', 'Paris').strip()
    
    current_wx = get_current_weather(destination_name)
    forecast_wx = get_weather_forecast(destination_name)
    
    return render_template('weather.html', 
                           destination=destination_name,
                           current=current_wx, 
                           forecast=forecast_wx.get('forecast', []))


@app.route('/attractions')
def attractions_map():
    destination_name = request.args.get('destination', 'Jaipur').strip()
    
    coords = geocode_location(destination_name)
    attraction_list = get_nearby_attractions(destination_name, limit=12)
    
    return render_template('attractions_map.html', 
                           destination=destination_name, 
                           coords=coords, 
                           attractions=attraction_list)


@app.route('/itinerary', methods=['GET', 'POST'])
def itinerary():
    form = ItineraryForm()
    
    if request.method == 'GET':
        dest_arg = request.args.get('destination', '')
        if dest_arg:
            form.destination.data = dest_arg
            
    days_plan = None
    destination_name = ""
    
    if form.validate_on_submit():
        destination_name = form.destination.data.strip()
        num_days = form.days.data
        user_budget = form.budget.data
        
        # Retrieve live & dataset attractions for destination
        raw_attractions = get_nearby_attractions(destination_name, limit=18)
        dest_coords = geocode_location(destination_name)
        c_lat, c_lng = dest_coords['lat'], dest_coords['lng']
        
        # --- NAIVE PROXIMITY SORTING ---
        # Note: Full route optimization (TSP / shortest path calculation) is planned for future enhancements.
        # Here we perform a spatial proximity sort based on Euclidean distance from destination center.
        def calc_distance(item):
            lat_diff = item.get('lat', c_lat) - c_lat
            lng_diff = item.get('lng', c_lng) - c_lng
            return math.sqrt(lat_diff**2 + lng_diff**2)
            
        sorted_attractions = sorted(raw_attractions, key=calc_distance)
        
        # Group 2-3 activities per day
        days_plan = []
        activities_per_day = 3
        
        time_slots = ["Morning (09:00 AM)", "Afternoon (01:30 PM)", "Evening (05:30 PM)"]
        
        attraction_idx = 0
        for day in range(1, num_days + 1):
            day_activities = []
            for slot in time_slots:
                if attraction_idx < len(sorted_attractions):
                    att = sorted_attractions[attraction_idx]
                    attraction_idx += 1
                else:
                    # Fallback activity generator if limit reached
                    att = {
                        'name': f"{destination_name} Local Explorer & Relaxation",
                        'category': 'Leisure',
                        'address': f"Downtown {destination_name}"
                    }
                day_activities.append({
                    'slot': slot,
                    'title': att.get('name'),
                    'category': att.get('category'),
                    'address': att.get('address')
                })
            days_plan.append({
                'day_number': day,
                'activities': day_activities
            })

    return render_template('itinerary.html', form=form, days_plan=days_plan, destination=destination_name)


@app.route('/community', methods=['GET', 'POST'])
def community():
    form = PostForm()
    comment_form = CommentForm()
    
    if request.method == 'POST' and form.validate_on_submit():
        if not current_user.is_authenticated:
            flash('Please log in to share posts with the community.', 'warning')
            return redirect(url_for('login'))
            
        location_input = sanitize_html(form.location_name.data)
        coords = geocode_location(location_input)
        
        image_filename = None
        if form.image.data and allowed_file(form.image.data.filename):
            file = form.image.data
            filename = secure_filename(f"post_{current_user.id}_{int(datetime.utcnow().timestamp())}_{file.filename}")
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            image_filename = filename

        post = Post(
            user_id=current_user.id,
            caption=sanitize_html(form.caption.data),
            location_name=location_input,
            lat=coords.get('lat'),
            lng=coords.get('lng'),
            image_path=image_filename
        )
        db.session.add(post)
        db.session.commit()
        flash('Your post has been published to the community feed!', 'success')
        return redirect(url_for('community'))

    posts = Post.query.order_by(Post.created_at.desc()).all()
    posts_data = [p.to_dict(current_user_id=current_user.id if current_user.is_authenticated else None) for p in posts]
    
    return render_template('community.html', form=form, comment_form=comment_form, posts=posts, posts_data=posts_data)


@app.route('/community/like/<int:post_id>', methods=['POST'])
@login_required
def like_post(post_id):
    post = db.get_or_404(Post, post_id)
    existing_like = Like.query.filter_by(user_id=current_user.id, post_id=post_id).first()
    
    if existing_like:
        db.session.delete(existing_like)
        db.session.commit()
        liked = False
    else:
        new_like = Like(user_id=current_user.id, post_id=post_id)
        db.session.add(new_like)
        db.session.commit()
        liked = True
        
    likes_count = len(post.likes)
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({'liked': liked, 'likes_count': likes_count})
        
    return redirect(url_for('community'))


@app.route('/community/comment/<int:post_id>', methods=['POST'])
@login_required
def add_comment(post_id):
    post = db.get_or_404(Post, post_id)
    comment_text = request.form.get('comment_text', '').strip()
    
    if comment_text:
        sanitized_comment = sanitize_html(comment_text)
        comment = Comment(
            user_id=current_user.id,
            post_id=post_id,
            comment_text=sanitized_comment
        )
        db.session.add(comment)
        db.session.commit()
        flash('Comment added.', 'success')
    else:
        flash('Comment cannot be empty.', 'warning')
        
    return redirect(url_for('community'))


# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
