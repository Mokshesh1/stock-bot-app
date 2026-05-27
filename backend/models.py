from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from cryptography.fernet import Fernet
import os
import bcrypt
import hashlib

db = SQLAlchemy()


# ==================== ENCRYPTION HELPER ====================

class EncryptedField:
    """Helper to encrypt/decrypt sensitive fields"""
    
    @staticmethod
    def get_cipher():
        """Get Fernet cipher from environment"""
        encryption_key = os.getenv('ENCRYPTION_KEY')
        if not encryption_key:
            raise ValueError(
                'ENCRYPTION_KEY not set in environment. '
                'Generate with: python -c "from cryptography.fernet import Fernet; '
                'print(Fernet.generate_key().decode())"'
            )
        return Fernet(encryption_key.encode())
    
    @staticmethod
    def encrypt(plaintext):
        """Encrypt a value"""
        if not plaintext:
            return None
        cipher = EncryptedField.get_cipher()
        return cipher.encrypt(plaintext.encode()).decode()
    
    @staticmethod
    def decrypt(ciphertext):
        """Decrypt a value"""
        if not ciphertext:
            return None
        cipher = EncryptedField.get_cipher()
        return cipher.decrypt(ciphertext.encode()).decode()


# ==================== USER MODEL ====================

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
        nullable=False,
        index=True
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    zerodha_key_encrypted = db.Column(
        db.Text,
        nullable=True,
        comment='Encrypted Zerodha API key'
    )

    subscription_tier = db.Column(
        db.String(20),
        default='free'
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        index=True
    )

    last_login = db.Column(
        db.DateTime,
        nullable=True
    )

    is_active = db.Column(
        db.Boolean,
        default=True
    )

    trades = db.relationship(
        'Trade',
        backref='user',
        lazy=True,
        cascade='all, delete-orphan'
    )

    watchlist = db.relationship(
        'Watchlist',
        backref='user',
        lazy=True,
        cascade='all, delete-orphan'
    )

    alerts = db.relationship(
        'Alert',
        backref='user',
        lazy=True,
        cascade='all, delete-orphan'
    )

    token_blacklist = db.relationship(
        'TokenBlacklist',
        backref='user',
        lazy=True,
        cascade='all, delete-orphan'
    )

    def set_password(self, password):
        """Hash password using bcrypt"""
        if not password or len(password) < 8:
            raise ValueError('Password must be at least 8 characters')
        
        # bcrypt.gensalt() returns a salt with work factor 12 (industry standard)
        salt = bcrypt.gensalt(rounds=12)
        self.password_hash = bcrypt.hashpw(
            password.encode('utf-8'),
            salt
        ).decode('utf-8')

    def check_password(self, password):
        """Verify password against bcrypt hash, with legacy SHA-256 fallback."""
        if not password or not self.password_hash:
            return False

        password_bytes = password.encode('utf-8')

        # bcrypt hashes begin with $2a$, $2b$, or $2y$
        if self.password_hash.startswith(('$2a$', '$2b$', '$2y$')):
            try:
                return bcrypt.checkpw(
                    password_bytes,
                    self.password_hash.encode('utf-8')
                )
            except ValueError:
                return False

        # Fallback for legacy SHA-256 password hashes.
        legacy_hash = hashlib.sha256(password_bytes).hexdigest()
        if legacy_hash == self.password_hash:
            # Upgrade legacy hash to bcrypt on first successful login.
            self.set_password(password)
            try:
                db.session.add(self)
                db.session.commit()
            except Exception:
                db.session.rollback()
            return True

        return False

    def set_zerodha_key(self, plaintext_key):
        """Encrypt and store Zerodha key"""
        if plaintext_key:
            self.zerodha_key_encrypted = EncryptedField.encrypt(plaintext_key)
        else:
            self.zerodha_key_encrypted = None

    def get_zerodha_key(self):
        """Decrypt and return Zerodha key"""
        if self.zerodha_key_encrypted:
            return EncryptedField.decrypt(self.zerodha_key_encrypted)
        return None

    def to_dict(self, include_sensitive=False):
        """Convert to dict (never include password hash or decrypted keys)"""
        data = {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'subscription_tier': self.subscription_tier,
            'created_at': self.created_at.isoformat(),
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'is_active': self.is_active,
        }
        
        # Only include encrypted key existence flag, not the key itself
        if include_sensitive:
            data['has_zerodha_key'] = bool(self.zerodha_key_encrypted)
        
        return data


# ==================== TRADE MODEL ====================

class Trade(db.Model):

    __tablename__ = 'trades'

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        nullable=False,
        index=True
    )

    symbol = db.Column(
        db.String(20),
        nullable=False,
        index=True
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
        default=datetime.utcnow,
        index=True
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
        default='open',
        index=True
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
            'entry_time': self.entry_time.isoformat(),
            'exit_time': self.exit_time.isoformat() if self.exit_time else None,
        }


# ==================== WATCHLIST MODEL ====================

class Watchlist(db.Model):

    __tablename__ = 'watchlist'

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        nullable=False,
        index=True
    )

    symbol = db.Column(
        db.String(20),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    __table_args__ = (
        db.UniqueConstraint('user_id', 'symbol', name='uq_user_symbol'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'symbol': self.symbol,
            'created_at': self.created_at.isoformat(),
        }


# ==================== ALERT MODEL ====================

class Alert(db.Model):

    __tablename__ = 'alerts'

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        nullable=False,
        index=True
    )

    symbol = db.Column(
        db.String(20),
        nullable=False,
        index=True
    )

    alert_type = db.Column(
        db.String(50),
        nullable=False
    )

    target_value = db.Column(
        db.Float,
        nullable=True
    )

    is_triggered = db.Column(
        db.Boolean,
        default=False,
        index=True
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        index=True
    )

    triggered_at = db.Column(
        db.DateTime,
        nullable=True
    )

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'symbol': self.symbol,
            'alert_type': self.alert_type,
            'target_value': self.target_value,
            'is_triggered': self.is_triggered,
            'created_at': self.created_at.isoformat(),
            'triggered_at': self.triggered_at.isoformat()
            if self.triggered_at
            else None,
        }


# ==================== TOKEN BLACKLIST MODEL ====================

class TokenBlacklist(db.Model):
    """Store invalidated JWT tokens (for logout support)"""

    __tablename__ = 'token_blacklist'

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id'),
        nullable=False,
        index=True
    )

    token_jti = db.Column(
        db.String(255),
        nullable=False,
        unique=True,
        index=True,
        comment='JWT jti (unique token ID)'
    )

    blacklisted_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        index=True
    )

    expires_at = db.Column(
        db.DateTime,
        nullable=False,
        index=True,
        comment='Token expiry time'
    )