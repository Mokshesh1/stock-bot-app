from dataclasses import dataclass
from typing import Optional, Tuple
import yfinance as yf
import pandas as pd
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

@dataclass
class RiskTargets:
    """Risk and target levels for a trade"""
    symbol: str
    signal: str  # BUY, SELL, HOLD
    entry_price: float
    
    # Take profit levels
    target_price_1: float  # First target (conservative)
    target_price_2: float  # Second target (aggressive)
    
    # Stop loss
    stop_loss: float
    
    # Risk metrics
    risk_reward_ratio: float  # TP1:SL ratio
    position_size_pct: float  # Recommended position size % based on risk
    
    # Volatility context
    atr_value: Optional[float]
    volatility_pct: float
    volatility_level: str  # Low, Medium, High
    
    # Explanation
    explanation: str

class RiskTargetEngine:
    """
    Calculates dynamic stop loss and take profit levels based on ATR and volatility
    Edge cases: Low volatility → widen SL; High volatility → enforce min R:R; Illiquid → block trade
    """
    
    def __init__(self, symbol: str):
        self.symbol = symbol
        self.data = None
        self.ticker = None
    
    def fetch_data(self) -> bool:
        """Fetch recent OHLC data for volatility calculation"""
        try:
            start_date = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
            self.data = yf.download(
                self.symbol,
                start=start_date,
                progress=False,
                timeout=10
            )
            
            self.ticker = yf.Ticker(self.symbol)
            
            if self.data is None or self.data.empty or len(self.data) < 14:
                logger.warning(f"Insufficient data for {self.symbol}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Failed to fetch risk data for {self.symbol}: {e}")
            return False
    
    def _calculate_atr(self, period: int = 14) -> Optional[float]:
        """Calculate Average True Range"""
        if self.data is None or len(self.data) < period:
            return None
        
        high = self.data['High']
        low = self.data['Low']
        close = self.data['Close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        
        return atr.iloc[-1]
    
    def _calculate_volatility(self) -> float:
        """Calculate volatility as percentage of current price"""
        if self.data is None or len(self.data) < 20:
            return 0
        
        close = self.data['Close']
        returns = close.pct_change()
        volatility = returns.std() * 100  # As percentage
        
        return volatility
    
    def _is_liquid_stock(self) -> Tuple[bool, str]:
        """Check if stock has sufficient liquidity"""
        try:
            market_cap = self.ticker.info.get('marketCap')
            avg_volume = self.data['Volume'].tail(20).mean()
            current_price = self.data['Close'].iloc[-1]
            
            # Minimum liquidity checks
            min_volume_usd = 100000  # $100k minimum daily volume
            daily_volume_usd = avg_volume * current_price
            
            if daily_volume_usd < min_volume_usd:
                return False, "Insufficient daily volume (USD)"
            
            return True, "Liquid"
        except Exception as e:
            logger.warning(f"Could not assess liquidity for {self.symbol}: {e}")
            return True, "Liquidity check skipped"  # Don't block on error
    
    def calculate_targets(
        self,
        entry_price: float,
        signal: str,  # BUY or SELL
        risk_pct: float = 1.0  # Risk % per trade
    ) -> Optional[RiskTargets]:
        """Calculate dynamic TP/SL levels"""
        
        if not self.fetch_data():
            return None
        
        # Check liquidity
        is_liquid, liquidity_msg = self._is_liquid_stock()
        if not is_liquid:
            logger.warning(f"Trade blocked: {liquidity_msg}")
            return None
        
        # Calculate volatility metrics
        atr = self._calculate_atr(14)
        volatility_pct = self._calculate_volatility()
        
        # Determine volatility level
        if volatility_pct < 1.5:
            volatility_level = "Low"
        elif volatility_pct < 3.0:
            volatility_level = "Medium"
        else:
            volatility_level = "High"
        
        # Base multipliers
        if signal == "BUY":
            # Long trade: SL below entry, TP above entry
            if volatility_level == "Low":
                # Widen SL for low volatility (edge case)
                sl_multiplier = 2.5
                tp1_multiplier = 1.5
                tp2_multiplier = 2.5
            elif volatility_level == "Medium":
                sl_multiplier = 2.0
                tp1_multiplier = 1.5
                tp2_multiplier = 2.5
            else:
                # High volatility: enforce min R:R of 1:1.5
                sl_multiplier = 1.5
                tp1_multiplier = 1.5
                tp2_multiplier = 2.5
            
            if atr:
                stop_loss = entry_price - (atr * sl_multiplier)
                target_price_1 = entry_price + (atr * tp1_multiplier)
                target_price_2 = entry_price + (atr * tp2_multiplier)
            else:
                # Fallback: use percentage-based
                stop_loss = entry_price * (1 - 0.02)  # 2% below
                target_price_1 = entry_price * (1 + 0.03)  # 3% above
                target_price_2 = entry_price * (1 + 0.05)  # 5% above
        
        elif signal == "SELL":
            # Short trade: SL above entry, TP below entry
            if volatility_level == "Low":
                sl_multiplier = 2.5
                tp1_multiplier = 1.5
                tp2_multiplier = 2.5
            elif volatility_level == "Medium":
                sl_multiplier = 2.0
                tp1_multiplier = 1.5
                tp2_multiplier = 2.5
            else:
                sl_multiplier = 1.5
                tp1_multiplier = 1.5
                tp2_multiplier = 2.5
            
            if atr:
                stop_loss = entry_price + (atr * sl_multiplier)
                target_price_1 = entry_price - (atr * tp1_multiplier)
                target_price_2 = entry_price - (atr * tp2_multiplier)
            else:
                stop_loss = entry_price * (1 + 0.02)
                target_price_1 = entry_price * (1 - 0.03)
                target_price_2 = entry_price * (1 - 0.05)
        
        else:
            return None  # HOLD signal
        
        # Calculate risk-reward ratio
        if signal == "BUY":
            risk = entry_price - stop_loss
            reward = target_price_1 - entry_price
        else:
            risk = stop_loss - entry_price
            reward = entry_price - target_price_1
        
        risk_reward_ratio = reward / risk if risk > 0 else 0
        
        # Enforce minimum R:R for high volatility
        if volatility_level == "High" and risk_reward_ratio < 1.5:
            # Adjust TP to meet 1.5:1 minimum
            if signal == "BUY":
                target_price_1 = entry_price + (risk * 1.5)
                target_price_2 = entry_price + (risk * 2.5)
            else:
                target_price_1 = entry_price - (risk * 1.5)
                target_price_2 = entry_price - (risk * 2.5)
            
            risk_reward_ratio = 1.5
        
        # Calculate position size based on risk
        position_size_pct = 100  # Full size by default
        if risk > 0:
            # Calculate position size to risk ~1% of account
            max_risk_per_trade = 1.0  # 1% max risk
            position_size_pct = min(100, (max_risk_per_trade / risk) * 100)
        
        # Build explanation
        explanation_parts = [
            f"Volatility: {volatility_level} ({volatility_pct:.2f}%)",
            f"ATR(14): {atr:.2f}" if atr else "ATR: N/A",
            f"Entry: {entry_price:.2f} | SL: {stop_loss:.2f} | TP1: {target_price_1:.2f} | TP2: {target_price_2:.2f}",
            f"Risk:Reward = 1:{risk_reward_ratio:.2f}",
            f"Suggested Position Size: {position_size_pct:.0f}% of capital"
        ]
        
        if volatility_level == "Low":
            explanation_parts.append("⚠️ Low volatility → SL widened for safety")
        elif volatility_level == "High":
            explanation_parts.append("⚠️ High volatility → enforced minimum 1.5:1 R:R")
        
        explanation = " | ".join(explanation_parts)
        
        return RiskTargets(
            symbol=self.symbol,
            signal=signal,
            entry_price=entry_price,
            target_price_1=target_price_1,
            target_price_2=target_price_2,
            stop_loss=stop_loss,
            risk_reward_ratio=risk_reward_ratio,
            position_size_pct=position_size_pct,
            atr_value=atr,
            volatility_pct=volatility_pct,
            volatility_level=volatility_level,
            explanation=explanation
        )

if __name__ == "__main__":
    # Test
    engine = RiskTargetEngine("RELIANCE.NS")
    targets = engine.calculate_targets(entry_price=2500, signal="BUY")
    if targets:
        print(f"Entry: {targets.entry_price:.2f}")
        print(f"Stop Loss: {targets.stop_loss:.2f}")
        print(f"Target 1: {targets.target_price_1:.2f}")
        print(f"Target 2: {targets.target_price_2:.2f}")
        print(f"Risk:Reward: 1:{targets.risk_reward_ratio:.2f}")
        print(f"\nExplanation: {targets.explanation}")
    else:
        print("Failed to calculate targets")
