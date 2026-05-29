from app import db
from datetime import datetime
import uuid

from werkzeug.security import generate_password_hash, check_password_hash

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'student' or 'admin'
    department = db.Column(db.String(100), nullable=True)
    complaints = db.relationship('Complaint', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
class Complaint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    ticket_id = db.Column(db.String(50), unique=True, nullable=False, default=lambda: str(uuid.uuid4())[:8].upper())
    # Optional identity
    name = db.Column(db.String(100), nullable=True) 
    category = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    evidence_file = db.Column(db.String(255), nullable=True)
    # Anonymous flag
    is_anonymous = db.Column(db.Boolean, default=False)
    # Status tracking
    status = db.Column(db.String(20), default="Pending")
    admin_reply = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
  
   
   

