from datetime import datetime, timezone
from typing import Optional, Dict, Any
from enum import Enum
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, JSON, Text, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import json
import logging

logger = logging.getLogger(__name__)
Base = declarative_base()

class AuditActionType(str, Enum):
    """Types of actions to audit"""
    USER_SIGNUP = "user_signup"
    USER_LOGIN = "user_login"
    USER_LOGIN_FAILED = "user_login_failed"
    USER_LOGOUT = "user_logout"
    PASSWORD_CHANGE = "password_change"
    TOKEN_REFRESH = "token_refresh"
    
    SIGNAL_GENERATED = "signal_generated"
    SIGNAL_VIEWED = "signal_viewed"
    STRATEGY_TESTED = "strategy_tested"
    
    PAPER_TRADE_OPENED = "paper_trade_opened"
    PAPER_TRADE_CLOSED = "paper_trade_closed"
    
    WATCHLIST_ADDED = "watchlist_added"
    WATCHLIST_REMOVED = "watchlist_removed"
    
    DATA_EXPORT = "data_export"
    ACCOUNT_DELETED = "account_deleted"

class AuditLog(Base):
    """Immutable audit log table"""
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    action = Column(String(50), nullable=False, index=True)  # AuditActionType
    resource_type = Column(String(50), nullable=True)  # 'signal', 'trade', 'user', etc.
    resource_id = Column(String(255), nullable=True)
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(String(500), nullable=True)
    details = Column(JSON, nullable=True)  # Additional context
    status = Column(String(20), nullable=False, default="success")  # success, failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    
    # Indexes for compliance queries
    __table_args__ = (
        Index('idx_user_action_created', 'user_id', 'action', 'created_at'),
        Index('idx_resource_created', 'resource_type', 'resource_id', 'created_at'),
    )

class SignalAuditLog(Base):
    """Detailed audit for signal generation (explainability)"""
    __tablename__ = "signal_audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    symbol = Column(String(10), nullable=False, index=True)
    signal_type = Column(String(20), nullable=False)  # 'technical', 'fundamental', 'sentiment', 'unified'
    
    # Signal scores
    technical_score = Column(Float, nullable=True)
    fundamental_score = Column(Float, nullable=True)
    sentiment_score = Column(Float, nullable=True)
    unified_score = Column(Float, nullable=False)
    final_signal = Column(String(10), nullable=False)  # BUY, SELL, HOLD
    confidence = Column(Float, nullable=False)  # 0-100
    
    # Explanation (explainability layer)
    technical_explanation = Column(Text, nullable=True)
    fundamental_explanation = Column(Text, nullable=True)
    sentiment_explanation = Column(Text, nullable=True)
    
    # Weighting used
    technical_weight = Column(Float, nullable=False)
    fundamental_weight = Column(Float, nullable=False)
    sentiment_weight = Column(Float, nullable=False)
    
    # Risk metrics
    risk_level = Column(String(20), nullable=True)  # low, medium, high
    target_price_1 = Column(Float, nullable=True)
    target_price_2 = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=True)
    
    # Data freshness
    data_age_seconds = Column(Integer, nullable=True)
    price_at_generation = Column(Float, nullable=True)
    
    # Metadata
    market_cap = Column(Float, nullable=True)
    volume = Column(Float, nullable=True)
    
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    
    __table_args__ = (
        Index('idx_symbol_created', 'symbol', 'created_at'),
        Index('idx_user_signal_created', 'user_id', 'symbol', 'created_at'),
    )

class AuditLogger:
    """Logs all user actions and signals for compliance and explainability"""
    
    def __init__(self, db_session):
        self.db = db_session
    
    def log_action(
        self,
        user_id: int,
        action: AuditActionType,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        status: str = "success",
        error_message: Optional[str] = None
    ) -> int:
        """Log a user action"""
        try:
            log = AuditLog(
                user_id=user_id,
                action=action.value if isinstance(action, AuditActionType) else action,
                resource_type=resource_type,
                resource_id=resource_id,
                ip_address=ip_address,
                user_agent=user_agent,
                details=details or {},
                status=status,
                error_message=error_message,
            )
            self.db.add(log)
            self.db.commit()
            return log.id
        except Exception as e:
            logger.error(f"Failed to log action: {e}")
            self.db.rollback()
            return 0
    
    def log_signal_generation(
        self,
        user_id: int,
        symbol: str,
        technical_score: Optional[float],
        fundamental_score: Optional[float],
        sentiment_score: Optional[float],
        unified_score: float,
        final_signal: str,
        confidence: float,
        technical_explanation: Optional[str] = None,
        fundamental_explanation: Optional[str] = None,
        sentiment_explanation: Optional[str] = None,
        technical_weight: float = 0.4,
        fundamental_weight: float = 0.35,
        sentiment_weight: float = 0.25,
        risk_level: Optional[str] = None,
        target_price_1: Optional[float] = None,
        target_price_2: Optional[float] = None,
        stop_loss: Optional[float] = None,
        data_age_seconds: Optional[int] = None,
        price_at_generation: Optional[float] = None,
        market_cap: Optional[float] = None,
        volume: Optional[float] = None,
    ) -> int:
        """Log signal generation with full explainability"""
        try:
            log = SignalAuditLog(
                user_id=user_id,
                symbol=symbol,
                signal_type="unified",
                technical_score=technical_score,
                fundamental_score=fundamental_score,
                sentiment_score=sentiment_score,
                unified_score=unified_score,
                final_signal=final_signal,
                confidence=confidence,
                technical_explanation=technical_explanation,
                fundamental_explanation=fundamental_explanation,
                sentiment_explanation=sentiment_explanation,
                technical_weight=technical_weight,
                fundamental_weight=fundamental_weight,
                sentiment_weight=sentiment_weight,
                risk_level=risk_level,
                target_price_1=target_price_1,
                target_price_2=target_price_2,
                stop_loss=stop_loss,
                data_age_seconds=data_age_seconds,
                price_at_generation=price_at_generation,
                market_cap=market_cap,
                volume=volume,
            )
            self.db.add(log)
            self.db.commit()
            return log.id
        except Exception as e:
            logger.error(f"Failed to log signal: {e}")
            self.db.rollback()
            return 0
    
    def get_user_audit_history(
        self,
        user_id: int,
        limit: int = 100,
        action: Optional[str] = None
    ):
        """Retrieve user's audit history (for data export requests)"""
        query = self.db.query(AuditLog).filter(AuditLog.user_id == user_id)
        if action:
            query = query.filter(AuditLog.action == action)
        return query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    
    def get_signal_history(
        self,
        user_id: int,
        symbol: Optional[str] = None,
        limit: int = 50
    ):
        """Get signal generation history for explainability"""
        query = self.db.query(SignalAuditLog).filter(SignalAuditLog.user_id == user_id)
        if symbol:
            query = query.filter(SignalAuditLog.symbol == symbol)
        return query.order_by(SignalAuditLog.created_at.desc()).limit(limit).all()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
