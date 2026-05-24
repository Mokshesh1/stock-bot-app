from fastapi import Request, HTTPException, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import time
from typing import Callable, Dict, Tuple
from functools import lru_cache
import os

# Rate limiter configuration
limiter = Limiter(key_func=get_remote_address)

class CSRFMiddleware:
    """CSRF protection middleware for form submissions"""
    
    # In-memory CSRF token storage (for demo; use Redis in production)
    _csrf_tokens: Dict[str, Tuple[str, float]] = {}
    TOKEN_EXPIRY = 3600  # 1 hour
    
    @staticmethod
    def generate_csrf_token() -> str:
        """Generate and store a CSRF token"""
        import secrets
        token = secrets.token_urlsafe(32)
        CSRFMiddleware._csrf_tokens[token] = (token, time.time())
        return token
    
    @staticmethod
    def validate_csrf_token(token: str) -> bool:
        """Validate a CSRF token"""
        if token not in CSRFMiddleware._csrf_tokens:
            return False
        
        stored_token, created_at = CSRFMiddleware._csrf_tokens[token]
        
        # Check expiry
        if time.time() - created_at > CSRFMiddleware.TOKEN_EXPIRY:
            del CSRFMiddleware._csrf_tokens[token]
            return False
        
        # Token is valid, remove it (single-use)
        del CSRFMiddleware._csrf_tokens[token]
        return True
    
    @staticmethod
    def cleanup_expired_tokens():
        """Remove expired tokens"""
        current_time = time.time()
        expired = [
            token for token, (_, created_at) in CSRFMiddleware._csrf_tokens.items()
            if current_time - created_at > CSRFMiddleware.TOKEN_EXPIRY
        ]
        for token in expired:
            del CSRFMiddleware._csrf_tokens[token]

class InputValidator:
    """Validates user inputs across the app"""
    
    VALID_STOCK_SYMBOLS = {
        # NSE stocks - will be extended from yfinance
        "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
        "SBIN", "HDFC", "LT", "ITC", "BAJAJFINSV"
    }
    
    @staticmethod
    def validate_symbol(symbol: str) -> bool:
        """Validate stock symbol"""
        if not symbol:
            return False
        # Remove .NS if present (yfinance format)
        clean_symbol = symbol.replace(".NS", "").upper()
        return len(clean_symbol) <= 10 and clean_symbol.isalpha()
    
    @staticmethod
    def validate_quantity(quantity: float) -> bool:
        """Validate trade quantity"""
        return 0 < quantity <= 1_000_000
    
    @staticmethod
    def validate_price(price: float) -> bool:
        """Validate price input"""
        return 0 < price <= 10_000_000
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """Basic email validation"""
        import re
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return re.match(pattern, email) is not None
    
    @staticmethod
    def validate_strategy_name(strategy: str) -> bool:
        """Validate strategy name"""
        valid_strategies = {"ema_crossover", "rsi", "macd", "unified_signal"}
        return strategy.lower() in valid_strategies

class RequestSanitizer:
    """Sanitize inputs to prevent injection attacks"""
    
    @staticmethod
    def sanitize_string(value: str, max_length: int = 255) -> str:
        """Remove potentially dangerous characters"""
        if not isinstance(value, str):
            return ""
        # Remove null bytes
        value = value.replace("\x00", "")
        # Limit length
        return value[:max_length].strip()
    
    @staticmethod
    def sanitize_symbol(symbol: str) -> str:
        """Sanitize stock symbol"""
        clean = symbol.upper().strip()
        # Only alphanumeric and hyphen
        clean = "".join(c for c in clean if c.isalnum() or c == "-")
        return clean[:10]

class SecurityHeaders:
    """Add security headers to responses"""
    
    @staticmethod
    def get_headers() -> dict:
        """Return recommended security headers"""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            "Referrer-Policy": "strict-origin-when-cross-origin"
        }

class RateLimitConfig:
    """Rate limiting configuration per endpoint"""
    
    SIGNAL_GENERATION = "10 per minute"  # Prevent abuse of signal generation
    AUTH_LOGIN = "5 per minute"  # Brute force protection
    AUTH_SIGNUP = "3 per minute"  # Prevent spam registration
    GENERAL_API = "100 per minute"  # General API rate limit

class AccountLockout:
    """Track failed login attempts and lockout"""
    
    _failed_attempts: Dict[str, Tuple[int, float]] = {}
    MAX_ATTEMPTS = 5
    LOCKOUT_DURATION = 900  # 15 minutes
    
    @staticmethod
    def record_failed_attempt(email: str):
        """Record a failed login attempt"""
        if email in AccountLockout._failed_attempts:
            attempts, first_attempt = AccountLockout._failed_attempts[email]
            AccountLockout._failed_attempts[email] = (attempts + 1, first_attempt)
        else:
            AccountLockout._failed_attempts[email] = (1, time.time())
    
    @staticmethod
    def reset_attempts(email: str):
        """Reset failed attempts on successful login"""
        if email in AccountLockout._failed_attempts:
            del AccountLockout._failed_attempts[email]
    
    @staticmethod
    def is_locked(email: str) -> bool:
        """Check if account is locked"""
        if email not in AccountLockout._failed_attempts:
            return False
        
        attempts, first_attempt = AccountLockout._failed_attempts[email]
        
        # Check if lockout period has expired
        if time.time() - first_attempt > AccountLockout.LOCKOUT_DURATION:
            del AccountLockout._failed_attempts[email]
            return False
        
        return attempts >= AccountLockout.MAX_ATTEMPTS
    
    @staticmethod
    def get_lockout_time_remaining(email: str) -> float:
        """Get remaining lockout time in seconds"""
        if email not in AccountLockout._failed_attempts:
            return 0
        
        attempts, first_attempt = AccountLockout._failed_attempts[email]
        if attempts < AccountLockout.MAX_ATTEMPTS:
            return 0
        
        remaining = AccountLockout.LOCKOUT_DURATION - (time.time() - first_attempt)
        return max(0, remaining)
