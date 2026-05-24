from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import hashlib

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    name = db.Column(
        db.String(100),
        nullable=False
    )

    email = db.Column(
        db.String(100),
        unique=True,
        nullable=False
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    zerodha_key = db.Column(
        db.String(255),
        nullable=True
    )

    subscription_tier = db.Column(
        db.String(20),
        default='free'
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    trades = db.relationship(
        'Trade',
        backref='user',
        lazy=True
    )

    watchlist = db.relationship(
        'Watchlist',
        backref='user',
        lazy=True
    )

    def set_password(self, password):
        self.password_hash = hashlib.sha256(
            password.encode()
        ).hexdigest()

    def check_password(self, password):
        return self.password_hash == hashlib.sha256(
            password.encode()
        ).hexdigest()

    def to_dict(self):

        return {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'subscription_tier':
                self.subscription_tier,
            'created_at':
                self.created_at.isoformat()
        }


class Trade(db.Model):

    __tablename__ = 'trades'

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        nullable=False
    )

    symbol = db.Column(
        db.String(20),
        nullable=False
    )

    entry_price = db.Column(
        db.Float,
        nullable=False
    )

    exit_price = db.Column(
        db.Float,
        nullable=True
    )

    quantity = db.Column(
        db.Integer,
        nullable=False
    )

    entry_time = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    exit_time = db.Column(
        db.DateTime,
        nullable=True
    )

    profit_loss = db.Column(
        db.Float,
        nullable=True
    )

    strategy = db.Column(
        db.String(50),
        nullable=False
    )

    status = db.Column(
        db.String(20),
        default='open'
    )

    def to_dict(self):

        return {

            'id': self.id,
            'symbol': self.symbol,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'quantity': self.quantity,
            'profit_loss': self.profit_loss,
            'strategy': self.strategy,
            'status': self.status,
            'entry_time':
                self.entry_time.isoformat()
        }


class Watchlist(db.Model):

    __tablename__ = 'watchlist'

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        nullable=False
    )

    symbol = db.Column(
        db.String(20),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    def to_dict(self):

        return {
            'id': self.id,
            'user_id': self.user_id,
            'symbol': self.symbol
        }