from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    profile_photo = db.Column(db.String(255), default='default_avatar.png')
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    joined_date = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    posts = db.relationship('Post', backref='author', lazy=True, cascade='all, delete-orphan')
    likes = db.relationship('Like', backref='user', lazy=True, cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='user', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.email} (Admin={self.is_admin})>'


class Destination(db.Model):
    __tablename__ = 'destinations'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    state = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    budget_level = db.Column(db.String(50), nullable=False)  # Budget, Moderate, Luxury
    description = db.Column(db.Text, nullable=False)
    tags = db.Column(db.String(255), nullable=True)

    # Relationship to hotel cache
    cached_hotels = db.relationship('HotelsCache', backref='destination', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'state': self.state,
            'category': self.category,
            'budget_level': self.budget_level,
            'description': self.description,
            'tags': self.tags
        }


class HotelsCache(db.Model):
    __tablename__ = 'hotels_cache'
    
    id = db.Column(db.Integer, primary_key=True)
    destination_id = db.Column(db.Integer, db.ForeignKey('destinations.id', ondelete='CASCADE'), nullable=False)
    hotel_name = db.Column(db.String(150), nullable=False)
    address = db.Column(db.String(255), nullable=True)
    rating = db.Column(db.Float, nullable=True)
    price_tier = db.Column(db.String(50), nullable=True)
    lat = db.Column(db.Float, nullable=True)
    lng = db.Column(db.Float, nullable=True)
    fetched_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'destination_id': self.destination_id,
            'hotel_name': self.hotel_name,
            'address': self.address,
            'rating': self.rating,
            'price_tier': self.price_tier,
            'lat': self.lat,
            'lng': self.lng,
            'fetched_at': self.fetched_at.strftime('%Y-%m-%d %H:%M') if self.fetched_at else ''
        }


class Post(db.Model):
    __tablename__ = 'posts'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    caption = db.Column(db.String(1000), nullable=False)
    image_path = db.Column(db.String(255), nullable=True)
    location_name = db.Column(db.String(150), nullable=True)
    lat = db.Column(db.Float, nullable=True)
    lng = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relationships
    likes = db.relationship('Like', backref='post', lazy=True, cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='post', lazy=True, cascade='all, delete-orphan')

    def to_dict(self, current_user_id=None):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'author_name': self.author.name if self.author else 'Traveler',
            'author_photo': self.author.profile_photo if self.author else 'default_avatar.png',
            'caption': self.caption,
            'image_path': self.image_path,
            'location_name': self.location_name,
            'lat': self.lat,
            'lng': self.lng,
            'created_at': self.created_at.strftime('%b %d, %Y %H:%M'),
            'likes_count': len(self.likes),
            'comments_count': len(self.comments),
            'is_liked_by_user': any(l.user_id == current_user_id for l in self.likes) if current_user_id else False
        }


class Like(db.Model):
    __tablename__ = 'likes'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id', ondelete='CASCADE'), nullable=False)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'post_id', name='unique_user_post_like'),
    )


class Comment(db.Model):
    __tablename__ = 'comments'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id', ondelete='CASCADE'), nullable=False)
    comment_text = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'author_name': self.user.name if self.user else 'Traveler',
            'author_photo': self.user.profile_photo if self.user else 'default_avatar.png',
            'comment_text': self.comment_text,
            'created_at': self.created_at.strftime('%b %d, %Y %H:%M')
        }
