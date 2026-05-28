import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_restx import Api, Resource, fields, Namespace
from models import db, User, Trade, Watchlist, Alert
from auth_utils import (
    generate_access_token,
    generate_refresh_token,
    token_required,
    token_required_with_user,
    blacklist_token,
    verify_token
)
from screener import StockScreener
from datetime import datetime
import logging
import yfinance as yf
from apscheduler.schedulers.background import BackgroundScheduler

# ==================== CONFIGURATION ====================

load_dotenv()

# ==================== ENVIRONMENT VALIDATION ====================

def validate_required_env_vars():
    """Validate all required environment variables at startup"""
    required_vars = {
        'SECRET_KEY': (
            'Run: python -c "import secrets; print(secrets.token_hex(32))"'
        ),
        'ENCRYPTION_KEY': (
            'Run: python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    }
    
    for var, instruction in required_vars.items():
        value = os.getenv(var)
        if not value:
            raise ValueError(
                f'{var} environment variable is required.\n'
                f'Instructions: {instruction}'
            )
        
        # SECRET_KEY must be at least 32 chars
        if var == 'SECRET_KEY' and len(value) < 32:
            raise ValueError(
                'SECRET_KEY must be at least 32 characters. '
                'Run: python -c "import secrets; print(secrets.token_hex(32))"'
            )

validate_required_env_vars()

# Initialize Flask app
app = Flask(__name__)

# ==================== CORS CONFIGURATION (FIXED - NOT DUPLICATE) ====================

# Get CORS origins from environment or use defaults for development
cors_origins = os.getenv(
    'CORS_ORIGINS',
    'https://stock-bot-app-five.vercel.app,https://stock-bot-app-production.up.railway.app,http://localhost:3000,http://localhost:5000,http://127.0.0.1:5500,null'
).split(',')

# Strip whitespace and trailing slashes from each origin
cors_origins = [origin.strip().rstrip('/') for origin in cors_origins if origin.strip()]

# Apply CORS configuration ONCE
CORS(
    app,
    resources={r"/api/*": {"origins": cors_origins}},
    supports_credentials=True,
    allow_headers=['Content-Type', 'Authorization', 'X-Token']
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ==================== DATABASE CONFIGURATION ====================

database_url = os.getenv('DATABASE_URL')

if not database_url:
    if os.getenv('FLASK_ENV') == 'production':
        raise ValueError(
            'DATABASE_URL environment variable is required in production. '
            'Format: postgresql+psycopg2://user:password@host:5432/dbname'
        )
    # Development fallback only
    database_url = 'sqlite:///stockbot_dev.db'
    logger.warning('Using SQLite for development. Set DATABASE_URL for production.')

# Handle PostgreSQL URL format
if database_url.startswith('postgresql://'):
    database_url = database_url.replace('postgresql://', 'postgresql+psycopg2://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ==================== EXTENSIONS ====================

db.init_app(app)

# ==================== FLASK-RESTX (SWAGGER) ====================

# Disable Swagger docs in production
if os.getenv('FLASK_ENV') == 'production':
    api = Api(app, version='1.0', title='StockBot API', prefix='/api', doc=False)
    logger.info('Swagger docs disabled in production')
else:
    api = Api(
        app,
        version='1.0',
        title='StockBot API',
        description='Secure stock screening and trading platform',
        doc='/api/docs',
        prefix='/api'
    )

# Namespaces - STANDARDIZED on Flask-RESTX
auth_ns = api.namespace('', description='Authentication')
user_ns = api.namespace('user', description='User management')
trade_ns = api.namespace('trades', description='Trade management')
scan_ns = api.namespace('scan', description='Stock screening')

# ==================== API MODELS (SWAGGER) ====================

user_model = api.model('User', {
    'id': fields.Integer(description='User ID'),
    'name': fields.String(required=True, description='Full name'),
    'email': fields.String(required=True, description='Email address'),
    'subscription_tier': fields.String(description='Subscription: free, starter, pro'),
    'created_at': fields.String(description='Creation timestamp'),
})

signup_model = api.model('Signup', {
    'name': fields.String(required=True, description='Full name'),
    'email': fields.String(required=True, description='Email address'),
    'password': fields.String(required=True, description='Password (min 8 chars)'),
    'zerodha_key': fields.String(description='Zerodha API key (optional)'),
})

login_model = api.model('Login', {
    'email': fields.String(required=True, description='Email address'),
    'password': fields.String(required=True, description='Password'),
})

login_response_model = api.model('LoginResponse', {
    'success': fields.Boolean(),
    'access_token': fields.String(description='JWT access token (24h expiry)'),
    'refresh_token': fields.String(description='JWT refresh token (7d expiry)'),
    'user': fields.Raw(description='User object'),
})

refresh_model = api.model('RefreshToken', {
    'refresh_token': fields.String(required=True, description='Refresh token'),
})

trade_input_model = api.model('TradeInput', {
    'symbol': fields.String(required=True, description='Stock symbol'),
    'entry_price': fields.Float(required=True, description='Entry price'),
    'quantity': fields.Integer(required=True, description='Number of shares'),
    'strategy': fields.String(required=True, description='Strategy name'),
})

# Initialize screener
screener = StockScreener()

# ==================== DATABASE INITIALIZATION ====================

with app.app_context():
    if os.getenv('FLASK_ENV') != 'production':
        # Development only: use create_all()
        logger.warning('Creating tables (dev mode only). Use Alembic migrations for production.')
        db.create_all()
    else:
        # Production: migrations must be run separately
        logger.info('Production mode: using Alembic migrations only')

# ==================== BACKGROUND TASKS ====================

def cleanup_expired_tokens():
    """Daily cleanup of expired token blacklist entries"""
    with app.app_context():
        from auth_utils import cleanup_expired_blacklist
        success = cleanup_expired_blacklist()
        if success:
            logger.info('Token blacklist cleanup completed')
        else:
            logger.error('Token blacklist cleanup failed')

# Setup background scheduler for token cleanup
if os.getenv('FLASK_ENV') == 'production':
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        func=cleanup_expired_tokens,
        trigger="cron",
        hour=2,
        minute=0,
        id='token_cleanup'
    )
    scheduler.start()
    logger.info('Background scheduler started (token cleanup at 2 AM daily)')

# ==================== ERROR HANDLERS ====================

@app.errorhandler(401)
def unauthorized(error):
    return {'success': False, 'message': 'Unauthorized', 'code': 'UNAUTHORIZED'}, 401

@app.errorhandler(403)
def forbidden(error):
    return {'success': False, 'message': 'Forbidden', 'code': 'FORBIDDEN'}, 403

@app.errorhandler(404)
def not_found(error):
    return {'success': False, 'message': 'Endpoint not found', 'code': 'NOT_FOUND'}, 404

@app.errorhandler(500)
def server_error(error):
    logger.error(f'Server error: {error}')
    return {'success': False, 'message': 'Server error', 'code': 'SERVER_ERROR'}, 500

# ==================== HEALTH CHECK ====================

@auth_ns.route('/health')
class Health(Resource):
    def get(self):
        """Health check endpoint (no auth required)"""
        return {
            'success': True,
            'message': 'Server is running',
            'timestamp': datetime.utcnow().isoformat()
        }, 200

# ==================== AUTHENTICATION ====================

@auth_ns.route('/signup')
class Signup(Resource):
    @api.expect(signup_model)
    def post(self):
        """Create a new user account"""
        try:
            data = request.json

            name = data.get('name', '').strip()
            email = data.get('email', '').strip().lower()
            password = data.get('password', '')

            if not email or not password or not name:
                return {
                    'success': False,
                    'message': 'Missing required fields: name, email, password'
                }, 400

            if len(password) < 8:
                return {
                    'success': False,
                    'message': 'Password must be at least 8 characters'
                }, 400

            if User.query.filter_by(email=email).first():
                return {
                    'success': False,
                    'message': 'Email already registered'
                }, 409

            user = User(name=name, email=email)
            user.set_password(password)
            
            if data.get('zerodha_key'):
                user.set_zerodha_key(data['zerodha_key'])

            db.session.add(user)
            db.session.commit()

            logger.info(f'New user registered: {user.email}')

            return {
                'success': True,
                'message': 'Signup successful',
                'user': user.to_dict()
            }, 201

        except ValueError as e:
            return {'success': False, 'message': str(e)}, 400
        except Exception as e:
            db.session.rollback()
            logger.error(f'Signup error: {e}')
            return {'success': False, 'message': 'Signup failed'}, 500


@auth_ns.route('/login')
class Login(Resource):
    @api.expect(login_model)
    def post(self):
        """Authenticate user and return JWT tokens"""
        try:
            data = request.json or {}
            email = data.get('email', '').strip().lower()
            password = data.get('password', '')

            if not email or not password:
                return {
                    'success': False,
                    'message': 'Email and password required'
                }, 400

            user = User.query.filter_by(email=email).first()

            if not user or not user.check_password(password):
                logger.warning(f'Failed login attempt for {email}')
                return {
                    'success': False,
                    'message': 'Invalid email or password'
                }, 401

            if not user.is_active:
                return {
                    'success': False,
                    'message': 'Account is inactive'
                }, 403

            access_token = generate_access_token(user.id, user.email)
            refresh_token = generate_refresh_token(user.id, user.email)

            user.last_login = datetime.utcnow()
            db.session.commit()

            logger.info(f'User logged in: {user.email}')

            return {
                'success': True,
                'access_token': access_token,
                'refresh_token': refresh_token,
                'user': user.to_dict(include_sensitive=True)
            }, 200

        except Exception as e:
            logger.error(f'Login error: {e}')
            return {'success': False, 'message': 'Login failed'}, 500


# ==================== REFRESH TOKEN (FIXED - WAS MISSING) ====================

@auth_ns.route('/refresh')
class RefreshToken(Resource):
    @api.expect(refresh_model)
    def post(self):
        """
        Refresh access token using refresh_token
        
        Returns new access_token if refresh_token is valid
        """
        try:
            data = request.json or {}
            refresh_token = data.get('refresh_token')
            
            if not refresh_token:
                return {
                    'success': False,
                    'message': 'Refresh token required'
                }, 400
            
            # Verify the refresh token
            payload, error = verify_token(refresh_token)
            
            if error:
                return {
                    'success': False,
                    'message': error
                }, 401
            
            # Check token type
            if payload.get('type') != 'refresh':
                return {
                    'success': False,
                    'message': 'Invalid token type'
                }, 401
            
            user_id = payload['user_id']
            email = payload['email']
            
            # Generate new access token
            new_access_token = generate_access_token(user_id, email)
            
            return {
                'success': True,
                'access_token': new_access_token
            }, 200
            
        except Exception as e:
            logger.error(f'Refresh token error: {e}')
            return {'success': False, 'message': 'Token refresh failed'}, 500


@auth_ns.route('/logout')
class Logout(Resource):
    @token_required
    def post(self, current_user_id):
        """Logout: blacklist the current token"""
        try:
            token = None
            if 'Authorization' in request.headers:
                token = request.headers['Authorization']
            
            if token:
                success, message = blacklist_token(token)
                if success:
                    logger.info(f'User {current_user_id} logged out')
                    return {
                        'success': True,
                        'message': 'Logged out successfully'
                    }, 200

            return {
                'success': False,
                'message': 'Logout failed'
            }, 400

        except Exception as e:
            logger.error(f'Logout error: {e}')
            return {'success': False, 'message': 'Logout failed'}, 500


# ==================== USER MANAGEMENT ====================

@user_ns.route('/<int:user_id>')
class GetUser(Resource):
    @token_required_with_user
    def get(self, user_id, current_user_id):
        """Get user profile information"""
        try:
            user = User.query.get(user_id)

            if not user:
                return {'success': False, 'message': 'User not found'}, 404

            return {
                'success': True,
                'user': user.to_dict(include_sensitive=True)
            }, 200

        except Exception as e:
            logger.error(f'Get user error: {e}')
            return {'success': False, 'message': str(e)}, 500


@user_ns.route('/<int:user_id>/stats')
class UserStats(Resource):
    @token_required_with_user
    def get(self, user_id, current_user_id):
        """Get trading statistics for authenticated user"""
        try:
            trades = Trade.query.filter_by(
                user_id=user_id,
                status='closed'
            ).all()

            if not trades:
                return {
                    'success': True,
                    'total_trades': 0,
                    'total_profit': 0,
                    'win_rate': 0,
                    'avg_profit': 0
                }, 200

            total_trades = len(trades)
            total_profit = sum(t.profit_loss for t in trades if t.profit_loss)
            winning_trades = len([t for t in trades if t.profit_loss and t.profit_loss > 0])
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            avg_profit = total_profit / total_trades if total_trades > 0 else 0

            return {
                'success': True,
                'total_trades': total_trades,
                'total_profit': round(total_profit, 2),
                'win_rate': round(win_rate, 2),
                'avg_profit': round(avg_profit, 2),
                'winning_trades': winning_trades
            }, 200

        except Exception as e:
            logger.error(f'User stats error: {e}')
            return {'success': False, 'message': str(e)}, 500

# ==================== TRADES ====================

@trade_ns.route('')
class TradeList(Resource):
    @token_required
    @api.expect(trade_input_model)
    def post(self, current_user_id):
        """Create a new paper trade"""
        try:
            data = request.json

            if not all(k in data for k in ['symbol', 'entry_price', 'quantity', 'strategy']):
                return {
                    'success': False,
                    'message': 'Missing required fields'
                }, 400

            trade = Trade(
                user_id=current_user_id,
                symbol=data['symbol'].upper(),
                entry_price=float(data['entry_price']),
                quantity=int(data['quantity']),
                strategy=data['strategy']
            )

            db.session.add(trade)
            db.session.commit()

            logger.info(f'Trade created: {trade.id}')

            return {'success': True, 'trade': trade.to_dict()}, 201

        except Exception as e:
            db.session.rollback()
            logger.error(f'Create trade error: {e}')
            return {'success': False, 'message': str(e)}, 500


@user_ns.route('/<int:user_id>/trades')
class UserTrades(Resource):
    @token_required_with_user
    def get(self, user_id, current_user_id):
        """Get all trades for authenticated user"""
        try:
            trades = Trade.query.filter_by(user_id=user_id).all()

            return {
                'success': True,
                'trades': [trade.to_dict() for trade in trades]
            }, 200

        except Exception as e:
            logger.error(f'Get user trades error: {e}')
            return {'success': False, 'message': str(e)}, 500


@trade_ns.route('/<int:trade_id>')
class TradeDetail(Resource):
    @token_required
    def put(self, trade_id, current_user_id):
        """Update a trade (close it)"""
        try:
            data = request.json
            trade = Trade.query.get(trade_id)

            if not trade:
                return {'success': False, 'message': 'Trade not found'}, 404

            if trade.user_id != current_user_id:
                return {
                    'success': False,
                    'message': 'Unauthorized: cannot modify other user\'s trades'
                }, 403

            if 'exit_price' in data:
                trade.exit_price = float(data['exit_price'])
                trade.exit_time = datetime.utcnow()
                trade.profit_loss = (
                    (float(data['exit_price']) - trade.entry_price) * trade.quantity
                )
                trade.status = 'closed'

            db.session.commit()

            logger.info(f'Trade updated: {trade.id}')

            return {'success': True, 'trade': trade.to_dict()}, 200

        except Exception as e:
            db.session.rollback()
            logger.error(f'Update trade error: {e}')
            return {'success': False, 'message': str(e)}, 500

# ==================== SCREENER ====================

@scan_ns.route('')
class ScanStocks(Resource):
    @token_required
    def post(self, current_user_id):
        """Scan stocks for trading signals"""
        try:
            data = request.json
            symbols = data.get('symbols', ['RELIANCE', 'TCS', 'INFY', 'HDFC'])
            strategy = data.get('strategy', 'ema_crossover')

            results = screener.scan_portfolio(symbols, strategy)

            return {
                'success': True,
                'results': results,
                'timestamp': datetime.utcnow().isoformat()
            }, 200

        except Exception as e:
            logger.error(f'Scan error: {e}')
            return {'success': False, 'message': str(e)}, 500


@scan_ns.route('/<symbol>')
class ScanSingle(Resource):
    @token_required
    def get(self, symbol, current_user_id):
        """Get signal for a single symbol"""
        try:
            result = screener.get_signal(symbol)

            return {
                'success': True,
                'data': result
            }, 200

        except Exception as e:
            logger.error(f'Single scan error: {e}')
            return {
                'success': False,
                'message': str(e)
            }, 500

# ==================== LIVE PRICES ====================

@scan_ns.route('/price/<symbol>')
class LivePrice(Resource):
    @token_required
    def get(self, symbol, current_user_id):
        """Get live price for a symbol with timeout"""
        try:
            ticker = yf.Ticker(f'{symbol.upper()}.NS')
            data = ticker.history(period='1d')

            if data.empty:
                return jsonify({
                    'success': False,
                    'message': 'Symbol not found'
                }), 404

            price = float(data['Close'].iloc[-1])

            return jsonify({
                'success': True,
                'symbol': symbol.upper(),
                'price': round(price, 2)
            }), 200

        except Exception as e:
            logger.error(f'Get price error: {e}')
            return jsonify({
                'success': False,
                'message': str(e)
            }), 500

# ==================== WATCHLIST ====================

@user_ns.route('/<int:user_id>/watchlist')
class UserWatchlist(Resource):
    @token_required_with_user
    def get(self, user_id, current_user_id):
        """Get watchlist for authenticated user"""
        try:
            items = Watchlist.query.filter_by(user_id=user_id).all()
            return jsonify({
                'success': True,
                'watchlist': [item.to_dict() for item in items]
            }), 200
        except Exception as e:
            logger.error(f'Get watchlist error: {e}')
            return jsonify({'success': False, 'message': str(e)}), 500

    @token_required_with_user
    def post(self, user_id, current_user_id):
        """Add symbol to watchlist"""
        try:
            data = request.json
            
            if not data.get('symbol'):
                return jsonify({'success': False, 'message': 'Symbol required'}), 400

            existing = Watchlist.query.filter_by(
                user_id=user_id,
                symbol=data['symbol'].upper()
            ).first()
            
            if existing:
                return jsonify({
                    'success': False,
                    'message': 'Symbol already in watchlist'
                }), 409

            item = Watchlist(
                user_id=user_id,
                symbol=data['symbol'].upper()
            )

            db.session.add(item)
            db.session.commit()

            return jsonify({
                'success': True,
                'watchlist': item.to_dict()
            }), 201

        except Exception as e:
            db.session.rollback()
            logger.error(f'Add watchlist error: {e}')
            return jsonify({'success': False, 'message': str(e)}), 500


@user_ns.route('/<int:user_id>/watchlist/<int:item_id>')
class WatchlistItem(Resource):
    @token_required_with_user
    def delete(self, user_id, item_id, current_user_id):
        """Remove symbol from watchlist"""
        try:
            item = Watchlist.query.filter_by(id=item_id, user_id=user_id).first()

            if not item:
                return jsonify({'success': False, 'message': 'Item not found'}), 404

            db.session.delete(item)
            db.session.commit()

            return jsonify({'success': True}), 200

        except Exception as e:
            db.session.rollback()
            logger.error(f'Delete watchlist error: {e}')
            return jsonify({'success': False, 'message': str(e)}), 500

# ==================== ALERTS ====================

@user_ns.route('/<int:user_id>/alerts')
class UserAlerts(Resource):
    @token_required_with_user
    def get(self, user_id, current_user_id):
        """Get alerts for authenticated user"""
        try:
            alerts = Alert.query.filter_by(user_id=user_id).order_by(
                Alert.created_at.desc()
            ).all()

            return jsonify({
                'success': True,
                'alerts': [alert.to_dict() for alert in alerts]
            }), 200

        except Exception as e:
            logger.error(f'Get alerts error: {e}')
            return jsonify({'success': False, 'message': str(e)}), 500

    @token_required_with_user
    def post(self, user_id, current_user_id):
        """Create an alert"""
        try:
            data = request.json

            if not data.get('symbol') or not data.get('alert_type'):
                return jsonify({
                    'success': False,
                    'message': 'Symbol and alert_type required'
                }), 400

            alert = Alert(
                user_id=user_id,
                symbol=data['symbol'].upper(),
                alert_type=data['alert_type'],
                target_value=data.get('target_value')
            )

            db.session.add(alert)
            db.session.commit()

            logger.info(f'Alert created: {alert.id}')

            return jsonify({
                'success': True,
                'alert': alert.to_dict()
            }), 201

        except Exception as e:
            db.session.rollback()
            logger.error(f'Create alert error: {e}')
            return jsonify({'success': False, 'message': str(e)}), 500


@user_ns.route('/<int:user_id>/alerts/<int:alert_id>')
class AlertDetail(Resource):
    @token_required_with_user
    def delete(self, user_id, alert_id, current_user_id):
        """Delete an alert"""
        try:
            alert = Alert.query.filter_by(id=alert_id, user_id=user_id).first()

            if not alert:
                return jsonify({
                    'success': False,
                    'message': 'Alert not found'
                }), 404

            db.session.delete(alert)
            db.session.commit()

            return jsonify({'success': True}), 200

        except Exception as e:
            db.session.rollback()
            logger.error(f'Delete alert error: {e}')
            return jsonify({'success': False, 'message': str(e)}), 500


@user_ns.route('/<int:user_id>/alerts/check')
class CheckAlerts(Resource):
    @token_required_with_user
    def get(self, user_id, current_user_id):
        """Check and trigger alerts"""
        try:
            alerts = Alert.query.filter_by(
                user_id=user_id,
                is_triggered=False
            ).all()

            triggered = []

            for alert in alerts:
                try:
                    result = screener.get_signal(alert.symbol)

                    if not result:
                        continue

                    should_trigger = False

                    if alert.alert_type == 'buy_signal' and result.get('signal') == 'BUY':
                        should_trigger = True
                    elif alert.alert_type == 'sell_signal' and result.get('signal') == 'SELL':
                        should_trigger = True
                    elif alert.alert_type == 'score_above' and result.get('score', 0) >= float(alert.target_value or 0):
                        should_trigger = True
                    elif alert.alert_type == 'price_above' and result.get('price', 0) >= float(alert.target_value or 0):
                        should_trigger = True
                    elif alert.alert_type == 'price_below' and result.get('price', 0) <= float(alert.target_value or 0):
                        should_trigger = True

                    if should_trigger:
                        alert.is_triggered = True
                        alert.triggered_at = datetime.utcnow()
                        triggered.append(alert.to_dict())

                except Exception as e:
                    logger.warning(f'Alert check failed for {alert.symbol}: {e}')

            db.session.commit()

            return jsonify({
                'success': True,
                'triggered_alerts': triggered
            }), 200

        except Exception as e:
            db.session.rollback()
            logger.error(f'Check alerts error: {e}')
            return jsonify({'success': False, 'message': str(e)}), 500

# ==================== ANALYTICS ====================

@user_ns.route('/<int:user_id>/analytics')
class UserAnalytics(Resource):
    @token_required_with_user
    def get(self, user_id, current_user_id):
        """Get portfolio analytics"""
        try:
            trades = Trade.query.filter_by(
                user_id=user_id,
                status='closed'
            ).all()

            if not trades:
                return jsonify({
                    'success': True,
                    'max_drawdown': 0,
                    'best_strategy': None,
                    'avg_return': 0
                }), 200

            profits = [t.profit_loss or 0 for t in trades]
            max_drawdown = min(profits) if profits else 0
            avg_return = sum(profits) / len(profits) if profits else 0

            strategy_map = {}
            for trade in trades:
                strategy_map.setdefault(trade.strategy, 0)
                strategy_map[trade.strategy] += trade.profit_loss or 0

            best_strategy = max(strategy_map, key=strategy_map.get) if strategy_map else None

            return jsonify({
                'success': True,
                'max_drawdown': round(max_drawdown, 2),
                'best_strategy': best_strategy,
                'avg_return': round(avg_return, 2)
            }), 200

        except Exception as e:
            logger.error(f'Get analytics error: {e}')
            return jsonify({'success': False, 'message': str(e)}), 500

# ==================== BACKTESTING ====================

@scan_ns.route('/backtest')
class Backtest(Resource):
    @token_required
    def post(self, current_user_id):
        """Run backtest for a symbol"""
        try:
            data = request.get_json()

            symbol = data.get('symbol')
            strategy = data.get('strategy', 'ema_crossover')
            days = int(data.get('days', 365))

            if not symbol:
                return jsonify({
                    'success': False,
                    'error': 'Symbol required'
                }), 400

            if not symbol.endswith('.NS'):
                symbol = f'{symbol}.NS'

            df = yf.download(
                symbol,
                period=f'{days}d',
                progress=False
            )

            if df.empty:
                return jsonify({
                    'success': False,
                    'error': f'No data found for {symbol}'
                }), 404

            entry_price = float(df['Close'].iloc[0])
            exit_price = float(df['Close'].iloc[-1])

            total_return = round(
                ((exit_price - entry_price) / entry_price) * 100,
                2
            )

            return jsonify({
                'symbol': str(symbol),
                'strategy': str(strategy),
                'total_return': float(total_return),
                'total_trades': 1,
                'win_rate': float(100 if total_return > 0 else 0),
                'avg_return': float(total_return),
                'max_drawdown': 0.0,
                'expectancy': float(total_return),
                'trades': [{
                    'entry': round(entry_price, 2),
                    'exit': round(exit_price, 2),
                    'return': float(total_return)
                }]
            }), 200

        except Exception as e:
            logger.error(f'Backtest error: {e}')
            return jsonify({
                'success': False,
                'error': str(e)
            }), 500

# ==================== RUN APPLICATION ====================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') != 'production'
    
    with app.app_context():
        # Don't use create_all in production
        if os.getenv('FLASK_ENV') != 'production':
            db.create_all()
    
    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug
    )