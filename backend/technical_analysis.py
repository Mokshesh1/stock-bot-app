import pandas as pd
import numpy as np
from typing import Optional, Tuple, Dict
from dataclasses import dataclass
from datetime import datetime, timedelta
import yfinance as yf
import logging

logger = logging.getLogger(__name__)

@dataclass
class TechnicalSignal:
    """Output of technical analysis"""
    ema_12: Optional[float]
    ema_26: Optional[float]
    rsi_14: Optional[float]
    macd_line: Optional[float]
    macd_signal: Optional[float]
    macd_histogram: Optional[float]
    atr_14: Optional[float]
    
    # Composite outputs
    trend: str  # Bullish, Bearish, Neutral
    signal: str  # BUY, SELL, HOLD
    score: float  # 0-100
    confidence: float  # 0-100
    volatility_level: str  # Low, Medium, High
    explanation: str

class TechnicalAnalysisEngine:
    """
    Calculates technical indicators: EMA, RSI, MACD, ATR
    Edge cases: Missing OHLC → exclude; Low volatility → force HOLD; Conflicting → downgrade confidence
    """
    
    def __init__(self, symbol: str, lookback_days: int = 100):
        """
        Args:
            symbol: Stock ticker (e.g., 'RELIANCE.NS')
            lookback_days: Days of historical data to fetch
        """
        self.symbol = symbol
        self.lookback_days = lookback_days
        self.data = None
        self.last_close = None
        self.data_fetch_time = None
    
    def fetch_data(self) -> bool:
        """Fetch OHLC data from yfinance"""
        try:
            start_date = (datetime.now() - timedelta(days=self.lookback_days)).strftime("%Y-%m-%d")
            self.data = yf.download(
                self.symbol,
                start=start_date,
                progress=False,
                timeout=10
            )
            self.data_fetch_time = datetime.now()
            
            if self.data is None or self.data.empty:
                logger.warning(f"No data for {self.symbol}")
                return False
            
            self.last_close = self.data['Close'].iloc[-1] if len(self.data) > 0 else None
            return True
        except Exception as e:
            logger.error(f"Failed to fetch data for {self.symbol}: {e}")
            return False
    
    def calculate_ema(self, period: int) -> Optional[pd.Series]:
        """Calculate Exponential Moving Average"""
        if self.data is None or len(self.data) < period:
            return None
        return self.data['Close'].ewm(span=period, adjust=False).mean()
    
    def calculate_rsi(self, period: int = 14) -> Optional[float]:
        """Calculate Relative Strength Index"""
        if self.data is None or len(self.data) < period + 1:
            return None
        
        close = self.data['Close']
        delta = close.diff()
        
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss.where(loss != 0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        
        return rsi.iloc[-1]
    
    def calculate_macd(self, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Calculate MACD, Signal Line, and Histogram"""
        if self.data is None or len(self.data) < slow:
            return None, None, None
        
        close = self.data['Close']
        ema_fast = close.ewm(span=fast, adjust=False).mean()
        ema_slow = close.ewm(span=slow, adjust=False).mean()
        
        macd_line = ema_fast - ema_slow
        macd_signal = macd_line.ewm(span=signal, adjust=False).mean()
        macd_histogram = macd_line - macd_signal
        
        return macd_line.iloc[-1], macd_signal.iloc[-1], macd_histogram.iloc[-1]
    
    def calculate_atr(self, period: int = 14) -> Optional[float]:
        """Calculate Average True Range (volatility)"""
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
    
    def _assess_ema_trend(self, ema_12: float, ema_26: float, last_close: float) -> Tuple[str, float]:
        """
        EMA Trend Assessment
        Returns: (trend, confidence_contribution)
        """
        if ema_12 > ema_26 > last_close:
            return "Bullish", 0.9
        elif ema_12 > ema_26:
            return "Bullish", 0.7
        elif ema_12 < ema_26 < last_close:
            return "Bearish", 0.9
        elif ema_12 < ema_26:
            return "Bearish", 0.7
        else:
            return "Neutral", 0.5
    
    def _assess_rsi_signal(self, rsi: float) -> Tuple[str, float]:
        """
        RSI Signal Assessment
        Oversold < 30, Neutral 30-70, Overbought > 70
        """
        if rsi < 30:
            return "BUY", 0.8  # Oversold
        elif rsi > 70:
            return "SELL", 0.8  # Overbought
        else:
            return "HOLD", 0.4
    
    def _assess_macd_signal(self, macd: float, signal_line: float, histogram: float) -> Tuple[str, float]:
        """
        MACD Signal Assessment
        Returns: (signal, confidence)
        """
        if macd > signal_line and histogram > 0:
            return "BUY", 0.7
        elif macd < signal_line and histogram < 0:
            return "SELL", 0.7
        else:
            return "HOLD", 0.3
    
    def generate_signal(self) -> Optional[TechnicalSignal]:
        """Generate complete technical signal"""
        
        # Fetch data
        if not self.fetch_data():
            return None
        
        # Calculate indicators
        ema_12_series = self.calculate_ema(12)
        ema_26_series = self.calculate_ema(26)
        rsi_14 = self.calculate_rsi(14)
        macd_line, macd_signal, macd_histogram = self.calculate_macd()
        atr_14 = self.calculate_atr(14)
        
        # Extract current values
        ema_12 = ema_12_series.iloc[-1] if ema_12_series is not None else None
        ema_26 = ema_26_series.iloc[-1] if ema_26_series is not None else None
        
        # Check for missing data
        if self.last_close is None or ema_12 is None or ema_26 is None:
            return None
        
        # Assess individual indicators
        trend, ema_confidence = self._assess_ema_trend(ema_12, ema_26, self.last_close)
        rsi_signal, rsi_confidence = self._assess_rsi_signal(rsi_14) if rsi_14 else ("HOLD", 0)
        macd_signal, macd_confidence = self._assess_macd_signal(macd_line, macd_signal, macd_histogram) if (macd_line and macd_signal) else ("HOLD", 0)
        
        # Determine volatility level
        volatility_pct = (atr_14 / self.last_close * 100) if atr_14 else 0
        if volatility_pct < 1:
            volatility_level = "Low"
            volatility_adjustment = "Force HOLD"  # Low volatility edge case
        elif volatility_pct < 2.5:
            volatility_level = "Medium"
            volatility_adjustment = ""
        else:
            volatility_level = "High"
            volatility_adjustment = ""
        
        # Consensus signal (majority voting with adjustments)
        signals = []
        if rsi_signal != "HOLD":
            signals.append(rsi_signal)
        if macd_signal != "HOLD":
            signals.append(macd_signal)
        
        if volatility_level == "Low":
            final_signal = "HOLD"
            confidence = 40
        elif trend == "Bullish":
            buy_count = signals.count("BUY")
            sell_count = signals.count("SELL")
            if buy_count >= sell_count:
                final_signal = "BUY"
            else:
                final_signal = "HOLD"
            confidence = 70 if buy_count > 0 else 50
        elif trend == "Bearish":
            buy_count = signals.count("BUY")
            sell_count = signals.count("SELL")
            if sell_count >= buy_count:
                final_signal = "SELL"
            else:
                final_signal = "HOLD"
            confidence = 70 if sell_count > 0 else 50
        else:
            final_signal = "HOLD"
            confidence = 40
        
        # Calculate score (0-100)
        score_map = {"BUY": 75, "SELL": 25, "HOLD": 50}
        base_score = score_map.get(final_signal, 50)
        score = base_score + (confidence - 50) / 2  # Adjust based on confidence
        score = max(0, min(100, score))
        
        # Build explanation
        explanation_parts = [
            f"EMA Trend: {trend}",
            f"RSI ({rsi_14:.1f}): {rsi_signal}",
            f"MACD: {macd_signal}",
            f"ATR ({volatility_pct:.2f}%): {volatility_level} volatility"
        ]
        if volatility_level == "Low":
            explanation_parts.append("⚠️ Low volatility detected → downgraded to HOLD")
        
        explanation = " | ".join(explanation_parts)
        
        return TechnicalSignal(
            ema_12=ema_12,
            ema_26=ema_26,
            rsi_14=rsi_14,
            macd_line=macd_line,
            macd_signal=macd_signal,
            macd_histogram=macd_histogram,
            atr_14=atr_14,
            trend=trend,
            signal=final_signal,
            score=score,
            confidence=confidence,
            volatility_level=volatility_level,
            explanation=explanation
        )

if __name__ == "__main__":
    # Test
    engine = TechnicalAnalysisEngine("RELIANCE.NS")
    signal = engine.generate_signal()
    if signal:
        print(f"Signal: {signal.signal} (Score: {signal.score:.1f}, Confidence: {signal.confidence:.0f}%)")
        print(f"Explanation: {signal.explanation}")
    else:
        print("Failed to generate signal")
