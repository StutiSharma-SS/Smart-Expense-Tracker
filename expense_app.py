import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import json
from functools import wraps

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:mysql#17@localhost/expense_tracker'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
CORS(app)

# Database Models
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    expenses = db.relationship('Expense', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    icon = db.Column(db.String(50), default='💰')
    color = db.Column(db.String(7), default='#007bff')
    
    expenses = db.relationship('Expense', backref='category', lazy=True)

class Expense(db.Model):
    __tablename__ = 'expenses'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    description = db.Column(db.String(200))
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        
        if User.query.filter_by(username=username).first():
            return jsonify({'success': False, 'message': 'Username already exists'})
        
        if User.query.filter_by(email=email).first():
            return jsonify({'success': False, 'message': 'Email already exists'})
        
        user = User(username=username, email=email)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Registration successful'})
    
    return render_template('auth.html', mode='register')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            return jsonify({'success': True, 'message': 'Login successful'})
        
        return jsonify({'success': False, 'message': 'Invalid credentials'})
    
    return render_template('auth.html', mode='login')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', username=session['username'])

# API Routes
@app.route('/api/expenses', methods=['GET'])
@login_required
def get_expenses():
    user_id = session['user_id']
    
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    category_id = request.args.get('category_id')
    
    query = Expense.query.filter_by(user_id=user_id)
    
    if start_date:
        query = query.filter(Expense.date >= start_date)
    if end_date:
        query = query.filter(Expense.date <= end_date)
    if category_id:
        query = query.filter_by(category_id=category_id)
    
    expenses = query.order_by(Expense.date.desc()).all()
    
    return jsonify([{
        'id': expense.id,
        'amount': float(expense.amount),
        'description': expense.description,
        'date': expense.date.strftime('%Y-%m-%d'),
        'category': {
            'id': expense.category.id,
            'name': expense.category.name,
            'icon': expense.category.icon,
            'color': expense.category.color
        }
    } for expense in expenses])

@app.route('/api/expenses', methods=['POST'])
@login_required
def add_expense():
    data = request.get_json()
    
    expense = Expense(
        user_id=session['user_id'],
        category_id=data['category_id'],
        amount=data['amount'],
        description=data.get('description', ''),
        date=datetime.strptime(data['date'], '%Y-%m-%d').date()
    )
    
    db.session.add(expense)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Expense added successfully'})

@app.route('/api/expenses/<int:expense_id>', methods=['PUT'])
@login_required
def update_expense(expense_id):
    expense = Expense.query.filter_by(id=expense_id, user_id=session['user_id']).first()
    
    if not expense:
        return jsonify({'success': False, 'message': 'Expense not found'})
    
    data = request.get_json()
    expense.category_id = data['category_id']
    expense.amount = data['amount']
    expense.description = data.get('description', '')
    expense.date = datetime.strptime(data['date'], '%Y-%m-%d').date()
    
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Expense updated successfully'})

@app.route('/api/expenses/<int:expense_id>', methods=['DELETE'])
@login_required
def delete_expense(expense_id):
    expense = Expense.query.filter_by(id=expense_id, user_id=session['user_id']).first()
    
    if not expense:
        return jsonify({'success': False, 'message': 'Expense not found'})
    
    db.session.delete(expense)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Expense deleted successfully'})

@app.route('/api/categories', methods=['GET'])
@login_required
def get_categories():
    categories = Category.query.all()
    return jsonify([{
        'id': cat.id,
        'name': cat.name,
        'icon': cat.icon,
        'color': cat.color
    } for cat in categories])

@app.route('/api/statistics', methods=['GET'])
@login_required
def get_statistics():
    user_id = session['user_id']
    now = datetime.now()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Monthly expenses
    monthly_expenses = db.session.query(
        db.func.sum(Expense.amount)
    ).filter(
        Expense.user_id == user_id,
        Expense.date >= start_of_month.date()
    ).scalar() or 0

    # ✅ Category-wise expenses (correct field alias)
    category_expenses = (
        db.session.query(
            Category.name.label("name"),
            Category.icon.label("icon"),
            Category.color.label("color"),
            db.func.coalesce(db.func.sum(Expense.amount), 0).label("amount")
        )
        .outerjoin(
            Expense,
            (Expense.category_id == Category.id) & (Expense.user_id == user_id)
        )
        .group_by(Category.id)
        .all()
    )

    # Monthly trend (last 6 months)
    monthly_trend = []
    for i in range(6):
        month_start = (now.replace(day=1) - timedelta(days=32 * i)).replace(day=1)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = month_start.replace(month=month_start.month % 12 + 1, day=1) - timedelta(days=1)

        month_total = db.session.query(
            db.func.sum(Expense.amount)
        ).filter(
            Expense.user_id == user_id,
            Expense.date >= month_start.date(),
            Expense.date <= month_end.date()
        ).scalar() or 0

        monthly_trend.append({
            "month": month_start.strftime("%b %Y"),
            "amount": float(month_total)
        })

    return jsonify({
        "monthly_total": float(monthly_expenses),
        "category_breakdown": [{
            "category": cat.name,
            "icon": cat.icon,
            "color": cat.color,
            "amount": float(cat.amount)
        } for cat in category_expenses],
        "monthly_trend": list(reversed(monthly_trend))
    })

def init_default_categories():
    default_categories = [
        {'name': 'Food & Dining', 'icon': '🍽️', 'color': '#FF6B6B'},
        {'name': 'Transportation', 'icon': '🚗', 'color': '#4ECDC4'},
        {'name': 'Shopping', 'icon': '🛍️', 'color': '#45B7D1'},
        {'name': 'Entertainment', 'icon': '🎬', 'color': '#96CEB4'},
        {'name': 'Bills & Utilities', 'icon': '💡', 'color': '#FFEAA7'},
        {'name': 'Healthcare', 'icon': '🏥', 'color': '#DDA0DD'},
        {'name': 'Education', 'icon': '📚', 'color': '#98D8C8'},
        {'name': 'Travel', 'icon': '✈️', 'color': '#F7DC6F'},
        {'name': 'Others', 'icon': '💰', 'color': '#BDC3C7'}
    ]
    
    for cat_data in default_categories:
        if not Category.query.filter_by(name=cat_data['name']).first():
            category = Category(**cat_data)
            db.session.add(category)
    
    db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        init_default_categories()
        print("Database initialized successfully!")
        print("Starting Smart Expense Tracker...")
        print("Visit: http://localhost:5000")
    
    app.run(debug=True, port=5000)
