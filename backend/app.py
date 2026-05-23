from flask import Flask, request, jsonify
from flask_cors import CORS
from models import db, User, Trade
from datetime import datetime, timedelta
import os
import secrets

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///stockbot.db'
app.config['SECRET_KEY'] = 'your-secret-key-change-this'

# Initialize database
db.init_app(app)
CORS(app)  # Enable CORS for frontend communication

# Create database tables
with app.app_context():
    db.create_all()


# ==================== API ENDPOINTS ====================

# 1. SIGNUP ENDPOINT
@app.route('/api/signup', methods=['POST'])
def signup():
    """Create a new user account"""
    try:
        data = request.json

        # Validate input
        if not data.get('email') or not data.get('password') or not data.get('name'):
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400

        # Check if user already exists
        if User.query.filter_by(email=data['email']).first():
            return jsonify({'success': False, 'message': 'Email already registered'}), 400

        # Create new user
        user = User(
            name=data['name'],
            email=data['email'],
            zerodha_key=data.get('zerodha_key', None) # Make it optional
        )
        user.set_password(data['password'])

        db.session.add(user)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Signup successful'}), 201

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# 2. LOGIN ENDPOINT
@app.route('/api/login', methods=['POST'])
def login():
    """Authenticate user and return token"""
    try:
        data = request.json

        # Find user
        user = User.query.filter_by(email=data['email']).first()

        if not user or not user.check_password(data['password']):
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

        # Generate token (simple version - use JWT in production)
        token = secrets.token_hex(16)

        return jsonify({
            'success': True,
            'token': token,
            'user': user.to_dict()
        }), 200

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# 3. GET USER INFO
@app.route('/api/user/<int:user_id>', methods=['GET'])
def get_user(user_id):
    """Get user information"""
    try:
        user = User.query.get(user_id)

        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404

        return jsonify({'success': True, 'user': user.to_dict()}), 200

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# 4. CREATE TRADE
@app.route('/api/trades', methods=['POST'])
def create_trade():
    """Create a new trade record"""
    try:
        data = request.json

        trade = Trade(
            user_id=data['user_id'],
            symbol=data['symbol'],
            entry_price=data['entry_price'],
            quantity=data['quantity'],
            strategy=data['strategy']
        )

        db.session.add(trade)
        db.session.commit()

        return jsonify({'success': True, 'trade': trade.to_dict()}), 201

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# 5. GET USER'S TRADES
@app.route('/api/user/<int:user_id>/trades', methods=['GET'])
def get_user_trades(user_id):
    """Get all trades for a user"""
    try:
        trades = Trade.query.filter_by(user_id=user_id).all()

        return jsonify({
            'success': True,
            'trades': [trade.to_dict() for trade in trades]
        }), 200

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# 6. UPDATE TRADE
@app.route('/api/trades/<int:trade_id>', methods=['PUT'])
def update_trade(trade_id):
    """Update a trade (close it, set exit price)"""
    try:
        data = request.json
        trade = Trade.query.get(trade_id)

        if not trade:
            return jsonify({'success': False, 'message': 'Trade not found'}), 404

        if 'exit_price' in data:
            trade.exit_price = data['exit_price']
            trade.exit_time = datetime.utcnow()

            # Calculate profit/loss
            trade.profit_loss = (data['exit_price'] - trade.entry_price) * trade.quantity
            trade.status = 'closed'

        db.session.commit()

        return jsonify({'success': True, 'trade': trade.to_dict()}), 200

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# 7. GET USER STATISTICS
@app.route('/api/user/<int:user_id>/stats', methods=['GET'])
def get_stats(user_id):
    """Calculate trading statistics for user"""
    try:
        trades = Trade.query.filter_by(user_id=user_id, status='closed').all()

        if not trades:
            return jsonify({
                'success': True,
                'total_trades': 0,
                'total_profit': 0,
                'win_rate': 0,
                'avg_profit': 0
            }), 200

        total_trades = len(trades)
        total_profit = sum(t.profit_loss for t in trades)
        winning_trades = len([t for t in trades if t.profit_loss > 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        avg_profit = total_profit / total_trades if total_trades > 0 else 0

        return jsonify({
            'success': True,
            'total_trades': total_trades,
            'total_profit': total_profit,
            'win_rate': round(win_rate, 2),
            'avg_profit': round(avg_profit, 2),
            'winning_trades': winning_trades
        }), 200

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# 8. HEALTH CHECK
@app.route('/api/health', methods=['GET'])
def health():
    """Check if server is running"""
    return jsonify({'success': True, 'message': 'Server is running'}), 200


# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'success': False, 'message': 'Not found'}), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({'success': False, 'message': 'Server error'}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)

from screener import StockScreener

screener = StockScreener()

# SCREENER ENDPOINT
@app.route('/api/scan', methods=['POST'])
def scan_stocks():
    """Scan stocks for trading signals"""
    try:
        data = request.json
        symbols = data.get('symbols', ['RELIANCE', 'TCS', 'INFY', 'HDFC'])
        strategy = data.get('strategy', 'ema_crossover')

        results = screener.scan_portfolio(symbols, strategy)

        return jsonify({
            'success': True,
            'results': results,
            'timestamp': datetime.utcnow().isoformat()
        }), 200

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/scan/<symbol>', methods=['GET'])
def scan_single_stock(symbol):
    """Get signal for single stock"""
    try:
        strategy = request.args.get('strategy', 'ema_crossover')

        if strategy == 'ema_crossover':
            result = screener.ema_crossover_signal(symbol)
        elif strategy == 'rsi':
            result = screener.rsi_signal(symbol)
        else:
            result = {'symbol': symbol, 'signal': 'UNKNOWN'}

        return jsonify({'success': True, 'data': result}), 200

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500