from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
import secrets
from typing import Optional
from pydantic import BaseModel, EmailStr
import re

class Settings:
    """Load from .env"""
    def __init__(self):
        from dotenv import load_dotenv
        import os
        load_dotenv()
        
        self.SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
        self.JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
        self.JWT_EXPIRATION_HOURS = int(os.getenv("JWT_EXPIRATION_HOURS", 24))
        self.JWT_REFRESH_EXPIRATION_DAYS = int(os.getenv("JWT_REFRESH_EXPIRATION_DAYS", 7))
        self.CSRF_SECRET = os.getenv("CSRF_SECRET", "change-me-in-production")
        self.DATABASE_URL = os.getenv("DATABASE_URL")
        self.ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

settings = Settings()

class PasswordValidator:
    """Validates password strength"""
    MIN_LENGTH = 12
    REQUIRE_UPPER = True
    REQUIRE_LOWER = True
    REQUIRE_DIGIT = True
    REQUIRE_SPECIAL = True
    
    @staticmethod
    def validate(password: str) -> tuple[bool, str]:
        """Returns (is_valid, error_message)"""
        if len(password) < PasswordValidator.MIN_LENGTH:
            return False, f"Password must be at least {PasswordValidator.MIN_LENGTH} characters"
        
        if PasswordValidator.REQUIRE_UPPER and not re.search(r"[A-Z]", password):
            return False, "Password must contain at least one uppercase letter"
        
        if PasswordValidator.REQUIRE_LOWER and not re.search(r"[a-z]", password):
            return False, "Password must contain at least one lowercase letter"
        
        if PasswordValidator.REQUIRE_DIGIT and not re.search(r"\d", password):
            return False, "Password must contain at least one digit"
        
        if PasswordValidator.REQUIRE_SPECIAL and not re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:',.<>?/`~]", password):
            return False, "Password must contain at least one special character (!@#$%^&*...)"
        
        return True, ""

class PasswordHasher:
    """Secure password hashing with bcrypt"""
    ROUNDS = 12  # bcrypt cost factor
    
    @staticmethod
    def hash(password: str) -> str:
        """Hash password with bcrypt"""
        salt = bcrypt.gensalt(rounds=PasswordHasher.ROUNDS)
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    @staticmethod
    def verify(password: str, hash_value: str) -> bool:
        """Verify password against hash"""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hash_value.encode('utf-8'))
        except Exception:
            return False

class TokenManager:
    """JWT token generation and verification"""
    
    @staticmethod
    def create_access_token(user_id: int, email: str) -> str:
        """Create JWT access token"""
        payload = {
            "user_id": user_id,
            "email": email,
            "type": "access",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRATION_HOURS)
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    
    @staticmethod
    def create_refresh_token(user_id: int, email: str) -> str:
        """Create JWT refresh token (longer expiry)"""
        payload = {
            "user_id": user_id,
            "email": email,
            "type": "refresh",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_EXPIRATION_DAYS)
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    
    @staticmethod
    def verify_token(token: str, token_type: str = "access") -> Optional[dict]:
        """Verify JWT token and return payload"""
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
            if payload.get("type") != token_type:
                return None
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
    
    @staticmethod
    def refresh_access_token(refresh_token: str) -> Optional[str]:
        """Generate new access token from refresh token"""
        payload = TokenManager.verify_token(refresh_token, token_type="refresh")
        if not payload:
            return None
        return TokenManager.create_access_token(payload["user_id"], payload["email"])

class CSRFTokenManager:
    """CSRF token generation and verification"""
    
    @staticmethod
    def generate_token() -> str:
        """Generate a CSRF token"""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def verify_token(token: str, stored_token: str) -> bool:
        """Verify CSRF token matches stored value"""
        try:
            return secrets.compare_digest(token, stored_token)
        except Exception:
            return False

# Pydantic schemas for auth
class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    confirm_password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int

class RefreshTokenRequest(BaseModel):
    refresh_token: str
