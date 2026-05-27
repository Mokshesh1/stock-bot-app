"""
JWT Authentication Utilities for StockBot

This module handles:
- JWT token generation (on login)
- JWT token validation (middleware)
- Token refresh
- Token blacklisting (logout)
"""

import os
import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, current_app
from models import db, TokenBlacklist


# ==================== JWT CONFIGURATION ====================

class JWTConfig:
    """JWT configuration"""
    
    ALGORITHM = 'HS256'
    ACCESS_TOKEN_EXPIRY_HOURS = 24
    REFRESH_TOKEN_EXPIRY_DAYS = 7
    
    @staticmethod
    def get_secret_key():
        """Get JWT secret from environment (required)"""
        secret = os.getenv('SECRET_KEY')
        if not secret:
            raise ValueError(
                'SECRET_KEY environment variable not set. '
                'Set it to a strong random string (min 32 characters).'
            )
        return secret


# ==================== TOKEN GENERATION ====================

def generate_access_token(user_id, email):
    """
    Generate a signed JWT access token
    
    Args:
        user_id: Integer user ID
        email: User email address
    
    Returns:
        Signed JWT token string
    """
    now = datetime.utcnow()
    expiry = now + timedelta(hours=JWTConfig.ACCESS_TOKEN_EXPIRY_HOURS)
    
    payload = {
        'user_id': user_id,
        'email': email,
        'iat': now,
        'exp': expiry,
        'jti': f"{user_id}_{now.timestamp()}",  # Unique token ID for blacklisting
        'type': 'access'
    }
    
    token = jwt.encode(
        payload,
        JWTConfig.get_secret_key(),
        algorithm=JWTConfig.ALGORITHM
    )
    
    return token


def generate_refresh_token(user_id, email):
    """
    Generate a signed JWT refresh token (longer expiry)
    
    Args:
        user_id: Integer user ID
        email: User email address
    
    Returns:
        Signed JWT token string
    """
    now = datetime.utcnow()
    expiry = now + timedelta(days=JWTConfig.REFRESH_TOKEN_EXPIRY_DAYS)
    
    payload = {
        'user_id': user_id,
        'email': email,
        'iat': now,
        'exp': expiry,
        'jti': f"{user_id}_refresh_{now.timestamp()}",
        'type': 'refresh'
    }
    
    token = jwt.encode(
        payload,
        JWTConfig.get_secret_key(),
        algorithm=JWTConfig.ALGORITHM
    )
    
    return token


# ==================== TOKEN VALIDATION ====================

def verify_token(token):
    """
    Verify and decode a JWT token
    
    Args:
        token: JWT token string (may include 'Bearer ' prefix)
    
    Returns:
        Tuple (decoded_payload, error_message)
        On success: (payload_dict, None)
        On error: (None, error_string)
    """
    if not token:
        return None, 'Token missing'
    
    # Strip 'Bearer ' prefix if present
    if token.startswith('Bearer '):
        token = token[7:]
    
    try:
        payload = jwt.decode(
            token,
            JWTConfig.get_secret_key(),
            algorithms=[JWTConfig.ALGORITHM]
        )
        
        # Check if token is blacklisted (logged out)
        jti = payload.get('jti')
        if jti and TokenBlacklist.query.filter_by(token_jti=jti).first():
            return None, 'Token has been revoked'
        
        return payload, None
        
    except jwt.ExpiredSignatureError:
        return None, 'Token has expired'
    except jwt.InvalidTokenError as e:
        return None, f'Invalid token: {str(e)}'
    except Exception as e:
        return None, f'Token verification failed: {str(e)}'


# ==================== DECORATORS ====================

def token_required(f):
    """
    Decorator to require valid JWT token on an endpoint
    
    Adds 'current_user_id' to function kwargs
    Usage:
        @app.route('/api/user/profile')
        @token_required
        def get_profile(current_user_id):
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Get token from Authorization header
        if 'Authorization' in request.headers:
            token = request.headers['Authorization']
        elif 'X-Token' in request.headers:
            token = request.headers['X-Token']
        
        if not token:
            return {
                'success': False,
                'message': 'Authorization token missing',
                'code': 'TOKEN_MISSING'
            }, 401
        
        payload, error = verify_token(token)
        
        if error:
            return {
                'success': False,
                'message': error,
                'code': 'INVALID_TOKEN'
            }, 401
        
        # Add current_user_id to kwargs
        kwargs['current_user_id'] = payload['user_id']
        
        return f(*args, **kwargs)
    
    return decorated


def token_required_with_user(f):
    """
    Decorator that requires valid JWT token AND validates user ownership
    
    Checks that path parameter user_id matches JWT claim
    Usage:
        @app.route('/api/user/<int:user_id>/stats')
        @token_required_with_user
        def get_stats(user_id, current_user_id):
            # current_user_id is automatically validated to equal user_id
            ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # First verify token
        token = None
        if 'Authorization' in request.headers:
            token = request.headers['Authorization']
        elif 'X-Token' in request.headers:
            token = request.headers['X-Token']
        
        if not token:
            return {
                'success': False,
                'message': 'Authorization token missing',
                'code': 'TOKEN_MISSING'
            }, 401
        
        payload, error = verify_token(token)
        if error:
            return {
                'success': False,
                'message': error,
                'code': 'INVALID_TOKEN'
            }, 401
        
        # Extract user_id from path parameter
        path_user_id = kwargs.get('user_id')
        token_user_id = payload['user_id']
        
        # Verify ownership: path user_id must match token user_id
        if path_user_id and path_user_id != token_user_id:
            return {
                'success': False,
                'message': 'Unauthorized: cannot access other user\'s data',
                'code': 'OWNERSHIP_MISMATCH'
            }, 403
        
        kwargs['current_user_id'] = token_user_id
        return f(*args, **kwargs)
    
    return decorated


# ==================== TOKEN BLACKLISTING (LOGOUT) ====================

def blacklist_token(token):
    """
    Blacklist a token (for logout)
    
    Args:
        token: JWT token string to revoke
    
    Returns:
        Tuple (success: bool, message: str)
    """
    payload, error = verify_token(token)
    
    if error:
        return False, error
    
    try:
        jti = payload.get('jti')
        user_id = payload.get('user_id')
        exp_timestamp = payload.get('exp')
        
        if not jti or not user_id:
            return False, 'Invalid token structure'
        
        # Create blacklist entry
        expires_at = datetime.fromtimestamp(exp_timestamp)
        
        entry = TokenBlacklist(
            user_id=user_id,
            token_jti=jti,
            expires_at=expires_at
        )
        
        db.session.add(entry)
        db.session.commit()
        
        return True, 'Token revoked successfully'
        
    except Exception as e:
        db.session.rollback()
        return False, f'Blacklist failed: {str(e)}'


def cleanup_expired_blacklist():
    """
    Clean up expired entries from token blacklist table
    (Run this periodically, e.g., daily cleanup job)
    """
    try:
        now = datetime.utcnow()
        TokenBlacklist.query.filter(
            TokenBlacklist.expires_at < now
        ).delete()
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        return False