import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_restx import Api, Resource, fields, Namespace
from models import db, User, Trade, Watchlist, Alert
from screener import StockScreener
from datetime import datetime
import secrets



# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Database configuration
database_url = os.getenv('DATABASE_URL')
if database_url:
    # Fix PostgreSQL URL format if needed
    if database_url.startswith('postgresql://'):
        database_url = database_url.replace('postgresql://', 'postgresql+psycopg2://', 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # Local development with SQLite
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///stockbot.db'

# Flask configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'moksh-trading-bot-secret')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions
db.init_app(app)
CORS(app)

# Initialize Flask-RESTX for Swagger documentation
api = Api(
    app,
    version='1.0',
    title='Stock Trading Bot API',
    description='API for stock screening, trading signals, and portfolio management',
    doc='/api/docs',  # Swagger UI at /api/docs
    prefix='/api'
)

# Create namespaces for organizing endpoints
auth_ns = api.namespace('', description='Authentication endpoints')
user_ns = api.namespace('user', description='User management')
trade_ns = api.namespace('trades', description='Trade management')
scan_ns = api.namespace('scan', description='Stock screening')

# Define models for Swagger documentation
user_model = api.model('User', {
    'id': fields.Integer(description='User ID'),
    'name': fields.String(required=True, description='Full name'),
    'email': fields.String(required=True, description='Email address'),
    'subscription_tier': fields.String(description='Subscription tier: free, starter, pro'),
    'created_at': fields.String(description='Creation timestamp'),
})

trade_model = api.model('Trade', {
    'id': fields.Integer(description='Trade ID'),
    'symbol': fields.String(required=True, description='Stock symbol'),
    'entry_price': fields.Float(required=True, description='Entry price'),
    'exit_price': fields.Float(description='Exit price'),
    'quantity': fields.Integer(required=True, description='Number of shares'),
    'profit_loss': fields.Float(description='Profit or loss amount'),
    'strategy': fields.String(required=True, description='Strategy used'),
    'status': fields.String(description='Trade status: open, closed'),
})

signup_model = api.model('Signup', {
    'name': fields.String(required=True, description='Full name'),
    'email': fields.String(required=True, description='Email address'),
    'password': fields.String(required=True, description='Password'),
    'zerodha_key': fields.String(description='Zerodha API key (optional)'),
})

login_model = api.model('Login', {
    'email': fields.String(required=True, description='Email address'),
    'password': fields.String(required=True, description='Password'),
})

trade_input_model = api.model('TradeInput', {
    'user_id': fields.Integer(required=True, description='User ID'),
    'symbol': fields.String(required=True, description='Stock symbol'),
    'entry_price': fields.Float(required=True, description='Entry price'),
    'quantity': fields.Integer(required=True, description='Number of shares'),
    'strategy': fields.String(required=True, description='Strategy name'),
})

# Initialize screener (commented out if having issues)
screener = StockScreener()

# Create database tables
with app.app_context():
    db.create_all()

# ==================== ROOT ENDPOINT ====================

# @app.route('/', methods=['GET'])
# def root():
  #  """Root endpoint - API info"""
   # return jsonify({
    #    'success': True,
     #   'message': 'Stock Trading Bot API',
      #  'version': '1.0',
       # 'documentation': '/api/docs',
        #'endpoints': {
         #   'health': '/api/health',
          #  'auth': '/api/signup, /api/login',
           # 'users': '/api/user/{user_id}',
            #'trades': '/api/trades, /api/user/{user_id}/trades',
            #'stats': '/api/user/{user_id}/stats',
       # }
   # }), 200

# ==================== HEALTH CHECK ====================

@auth_ns.route('/health')
class Health(Resource):
    def get(self):
        """Check if server is running"""
        return {'success': True, 'message': 'Server is running'}, 200

# ==================== AUTHENTICATION ====================

@auth_ns.route('/signup')
class Signup(Resource):
    @api.doc('signup')
    @api.expect(signup_model)
    def post(self):
        """Create a new user account"""
        try:
            data = request.json

            # Validate input
            if not data.get('email') or not data.get('password') or not data.get('name'):
                return {'success': False, 'message': 'Missing required fields'}, 400

            # Check if user already exists
            if User.query.filter_by(email=data['email']).first():
                return {'success': False, 'message': 'Email already registered'}, 400

            # Create new user
            user = User(
                name=data['name'],
                email=data['email'],
                zerodha_key=data.get('zerodha_key', None)
            )
            user.set_password(data['password'])

            db.session.add(user)
            db.session.commit()

            return {'success': True, 'message': 'Signup successful'}, 201

        except Exception as e:
            db.session.rollback()
            return {'success': False, 'message': str(e)}, 500


@auth_ns.route('/login')
class Login(Resource):
    @api.doc('login')
    @api.expect(login_model)
    def post(self):
        """Authenticate user and return token"""
        try:
            data = request.json

            # Find user
            user = User.query.filter_by(email=data['email']).first()

            if not user or not user.check_password(data['password']):
                return {'success': False, 'message': 'Invalid credentials'}, 401

            # Generate token
            token = secrets.token_hex(16)

            return {
                'success': True,
                'token': token,
                'user': user.to_dict()
            }, 200

        except Exception as e:
            return {'success': False, 'message': str(e)}, 500

# ==================== USER MANAGEMENT ====================

@user_ns.route('/<int:user_id>')
class GetUser(Resource):
    @api.doc('get_user')
    def get(self, user_id):
        """Get user information"""
        try:
            user = User.query.get(user_id)

            if not user:
                return {'success': False, 'message': 'User not found'}, 404

            return {'success': True, 'user': user.to_dict()}, 200

        except Exception as e:
            return {'success': False, 'message': str(e)}, 500


@user_ns.route('/<int:user_id>/stats')
class UserStats(Resource):
    @api.doc('get_user_stats')
    def get(self, user_id):
        """Get trading statistics for user"""
        try:
            trades = Trade.query.filter_by(user_id=user_id, status='closed').all()

            if not trades:
                return {
                    'success': True,
                    'total_trades': 0,
                    'total_profit': 0,
                    'win_rate': 0,
                    'avg_profit': 0
                }, 200

            total_trades = len(trades)
            total_profit = sum(t.profit_loss for t in trades)
            winning_trades = len([t for t in trades if t.profit_loss > 0])
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            avg_profit = total_profit / total_trades if total_trades > 0 else 0

            return {
                'success': True,
                'total_trades': total_trades,
                'total_profit': total_profit,
                'win_rate': round(win_rate, 2),
                'avg_profit': round(avg_profit, 2),
                'winning_trades': winning_trades
            }, 200

        except Exception as e:
            return {'success': False, 'message': str(e)}, 500

# ==================== TRADES ====================

@trade_ns.route('')
class TradeList(Resource):
    @api.doc('create_trade')
    @api.expect(trade_input_model)
    def post(self):
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

            return {'success': True, 'trade': trade.to_dict()}, 201

        except Exception as e:
            db.session.rollback()
            return {'success': False, 'message': str(e)}, 500


@user_ns.route('/<int:user_id>/trades')
class UserTrades(Resource):
    @api.doc('get_user_trades')
    def get(self, user_id):
        """Get all trades for a user"""
        try:
            trades = Trade.query.filter_by(user_id=user_id).all()

            return {
                'success': True,
                'trades': [trade.to_dict() for trade in trades]
            }, 200

        except Exception as e:
            return {'success': False, 'message': str(e)}, 500


@trade_ns.route('/<int:trade_id>')
class TradeDetail(Resource):
    @api.doc('update_trade')
    def put(self, trade_id):
        """Update a trade (close it, set exit price)"""
        try:
            data = request.json
            trade = Trade.query.get(trade_id)

            if not trade:
                return {'success': False, 'message': 'Trade not found'}, 404

            if 'exit_price' in data:
                trade.exit_price = data['exit_price']
                trade.exit_time = datetime.utcnow()
                trade.profit_loss = (data['exit_price'] - trade.entry_price) * trade.quantity
                trade.status = 'closed'

            db.session.commit()

            return {'success': True, 'trade': trade.to_dict()}, 200

        except Exception as e:
            db.session.rollback()
            return {'success': False, 'message': str(e)}, 500

# ==================== SCREENER (COMMENTED OUT) ====================
# Uncomment these when screener is working

@scan_ns.route('')
class ScanStocks(Resource):
    @api.doc('scan_stocks')
    def post(self):
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
            return {'success': False, 'message': str(e)}, 500


@scan_ns.route('/<symbol>')
class ScanSingle(Resource):

    def get(
        self,
        symbol
    ):

        try:

            result = screener.get_signal(
                symbol
            )

            return {

                'success': True,

                'data': result

            }, 200

        except Exception as e:

            return {

                'success': False,

                'message': str(e)

            }, 500

# Full app.py is large, so keep your existing file
# and ADD these routes below your current trade routes.

from models import db, User, Trade, Watchlist
import yfinance as yf

@app.route('/api/price/<symbol>', methods=['GET'])

def get_live_price(symbol):

    try:

        ticker = yf.Ticker(
            f'{symbol.upper()}.NS'
        )

        data = ticker.history(
            period='1d'
        )

        if data.empty:

            return jsonify({

                'success': False,
                'message':
                    'Symbol not found'

            }), 404

        price = float(
            data['Close'].iloc[-1]
        )

        return jsonify({

            'success': True,
            'symbol':
                symbol.upper(),

            'price':
                round(price,2)

        })

    except Exception as e:

        return jsonify({

            'success': False,
            'message':
                str(e)

        }), 500

@app.route(
    '/api/user/<int:user_id>/watchlist',
    methods=['GET']
)
def get_watchlist(user_id):

    items = Watchlist.query.filter_by(
        user_id=user_id
    ).all()

    return jsonify({

        'success': True,

        'watchlist': [

            item.to_dict()
            for item in items

        ]

    })


@app.route(
    '/api/user/<int:user_id>/watchlist',
    methods=['POST']
)
def add_watchlist(user_id):

    data = request.json

    item = Watchlist(

        user_id=user_id,
        symbol=data['symbol']

    )

    db.session.add(item)

    db.session.commit()

    return jsonify({

        'success': True,
        'watchlist':
            item.to_dict()

    })

# ==================== ALERTS ====================

@app.route(
    '/api/user/<int:user_id>/alerts',
    methods=['GET']
)
def get_alerts(user_id):

    alerts = Alert.query.filter_by(
        user_id=user_id
    ).order_by(
        Alert.created_at.desc()
    ).all()

    return jsonify({

        'success': True,

        'alerts': [

            alert.to_dict()
            for alert in alerts

        ]

    })


@app.route(
    '/api/user/<int:user_id>/alerts',
    methods=['POST']
)
def create_alert(user_id):

    try:

        data = request.json

        alert = Alert(

            user_id=user_id,

            symbol=data['symbol'].upper(),

            alert_type=data['alert_type'],

            target_value=data.get(
                'target_value'
            )

        )

        db.session.add(alert)

        db.session.commit()

        return jsonify({

            'success': True,

            'alert':
                alert.to_dict()

        }), 201

    except Exception as e:

        db.session.rollback()

        return jsonify({

            'success': False,

            'message': str(e)

        }), 500


@app.route(
    '/api/user/<int:user_id>/alerts/<int:alert_id>',
    methods=['DELETE']
)
def delete_alert(
    user_id,
    alert_id
):

    alert = Alert.query.filter_by(

        id=alert_id,
        user_id=user_id

    ).first()

    if not alert:

        return jsonify({

            'success': False,
            'message':
                'Alert not found'

        }), 404

    db.session.delete(alert)

    db.session.commit()

    return jsonify({

        'success': True

    })


@app.route(
    '/api/user/<int:user_id>/alerts/check',
    methods=['GET']
)
def check_alerts(user_id):

    alerts = Alert.query.filter_by(

        user_id=user_id,
        is_triggered=False

    ).all()

    triggered = []

    for alert in alerts:

        try:

            result = screener.scan_stock(
                alert.symbol
            )

            if not result:
                continue

            should_trigger = False

            if alert.alert_type == 'buy_signal':

                if result.get(
                    'signal'
                ) == 'BUY':

                    should_trigger = True

            elif alert.alert_type == 'sell_signal':

                if result.get(
                    'signal'
                ) == 'SELL':

                    should_trigger = True

            elif alert.alert_type == 'score_above':

                if result.get(
                    'score', 0
                ) >= float(
                    alert.target_value
                ):

                    should_trigger = True

            elif alert.alert_type == 'price_above':

                if result.get(
                    'price', 0
                ) >= float(
                    alert.target_value
                ):

                    should_trigger = True

            elif alert.alert_type == 'price_below':

                if result.get(
                    'price', 0
                ) <= float(
                    alert.target_value
                ):

                    should_trigger = True

            if should_trigger:

                alert.is_triggered = True

                alert.triggered_at = datetime.utcnow()

                triggered.append(
                    alert.to_dict()
                )

        except Exception as e:

            print(
                f'Alert check failed: {e}'
            )

    db.session.commit()

    return jsonify({

        'success': True,

        'triggered_alerts':
            triggered

    })

@app.route(
    '/api/user/<int:user_id>/analytics'
)
def get_analytics(user_id):

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

        })

    profits = [

        t.profit_loss or 0
        for t in trades

    ]

    max_drawdown = min(profits)

    avg_return = sum(profits) / len(profits)

    strategy_map = {}

    for trade in trades:

        strategy_map.setdefault(
            trade.strategy,
            0
        )

        strategy_map[
            trade.strategy
        ] += trade.profit_loss or 0

    best_strategy = max(
        strategy_map,
        key=strategy_map.get
    )

    return jsonify({

        'success': True,

        'max_drawdown':
            round(max_drawdown,2),

        'best_strategy':
            best_strategy,

        'avg_return':
            round(avg_return,2)

    })
@app.route(
    '/api/user/<int:user_id>/watchlist/<int:item_id>',
    methods=['DELETE']
)
def delete_watchlist_item(
    user_id,
    item_id
):

    item = Watchlist.query.filter_by(
        id=item_id,
        user_id=user_id
    ).first()

    if not item:

        return jsonify({
            'success': False
        }), 404

    db.session.delete(item)

    db.session.commit()

    return jsonify({
        'success': True
    })

# ==================== BACKTEST ====================

@app.route('/api/backtest', methods=['POST'])
def run_backtest():

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
                'error': f'No historical data found for {symbol}'
            }), 404

        df['EMA20'] = df['Close'].ewm(span=20).mean()
        df['EMA50'] = df['Close'].ewm(span=50).mean()

        total_return = round(
            (
                (df['Close'].iloc[-1] - df['Close'].iloc[0])
                / df['Close'].iloc[0]
            ) * 100,
            2
        )

        return jsonify({

            'symbol': symbol,

            'strategy': strategy,

            'total_return': total_return,

            'total_trades': 0,

            'win_rate': 0,

            'avg_return': total_return,

            'max_drawdown': 0,

            'expectancy': 0,

            'trades': []

        })

    except Exception as e:

        print(f'Backtest error: {e}')

        return jsonify({

            'success': False,

            'error': str(e)

        }), 500

# ==================== ERROR HANDLERS ====================

@app.errorhandler(404)
def not_found(error):
    return {'success': False, 'message': 'Endpoint not found'}, 404


@app.errorhandler(500)
def server_error(error):
    return {'success': False, 'message': 'Server error'}, 500


# ==================== RUN APPLICATION ====================

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    app.run(debug=False, port=port)