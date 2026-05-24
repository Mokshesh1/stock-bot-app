import yfinance as yf
import pandas as pd
import numpy as np
from typing import Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

@dataclass
class SentimentSignal:
    """Output of sentiment analysis"""
    volume_sentiment: str  # Bullish, Neutral, Bearish
    volume_score: float    # 0-100
    
    price_momentum: str    # Bullish, Neutral, Bearish
    momentum_score: float  # 0-100
    
    volatility_expectation: str  # Rising, Stable, Falling
    volatility_score: float      # 0-100
    
    signal: str  # BUY, SELL, HOLD
    score: float  # 0-100
    confidence: float  # 0-100
    explanation: str

class SentimentAnalysisEngine:
    """
    Analyzes market sentiment using volume-based proxy signals
    (Since we only have yfinance, we use volume, price momentum, and volatility trends)
    
    Edge cases: No data → neutral 50; Pump detection → cap score; Divergent signals → reduce weight
    """
    
    def __init__(self, symbol: str, lookback_days: int = 60):
        """
        Args:
            symbol: Stock ticker (e.g., 'RELIANCE.NS')
            lookback_days: Days of historical data to analyze
        """
        self.symbol = symbol
        self.lookback_days = lookback_days
        self.data = None
    
    def fetch_data(self) -> bool:
        """Fetch OHLCV data from yfinance"""
        try:
            start_date = (datetime.now() - timedelta(days=self.lookback_days)).strftime("%Y-%m-%d")
            self.data = yf.download(
                self.symbol,
                start=start_date,
                progress=False,
                timeout=10
            )
            
            if self.data is None or self.data.empty or len(self.data) < 5:
                logger.warning(f"Insufficient data for {self.symbol}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Failed to fetch sentiment data for {self.symbol}: {e}")
            return False
    
    def _detect_pump_and_dump(self) -> Tuple[bool, str]:
        """Detect potential pump-and-dump or manipulation"""
        if self.data is None or len(self.data) < 5:
            return False, ""
        
        recent_returns = (self.data['Close'].pct_change().tail(5) * 100)
        recent_volume_spike = self.data['Volume'].tail(5).std() / self.data['Volume'].tail(5).mean()
        
        # Detection: >30% move in 5 days + volume spike
        large_move = recent_returns.abs().max() > 30
        high_volume_volatility = recent_volume_spike > 2.0
        
        if large_move and high_volume_volatility:
            return True, "⚠️ Potential pump detected - sentiment score capped"
        
        return False, ""
    
    def _analyze_volume_sentiment(self) -> Tuple[str, float]:
        """Analyze volume-based sentiment"""
        if self.data is None or 'Volume' not in self.data.columns:
            return "Neutral", 50
        
        volume = self.data['Volume']
        
        # Calculate volume metrics
        avg_volume_20 = volume.tail(20).mean()
        current_volume = volume.iloc[-1]
        volume_ratio = current_volume / avg_volume_20 if avg_volume_20 > 0 else 1
        
        # Volume trend
        recent_volumes = volume.tail(10)
        volume_trend = "Rising" if recent_volumes.iloc[-1] > recent_volumes.mean() else "Falling"
        
        # Sentiment scoring
        score = 50  # Neutral baseline
        
        if volume_ratio > 2.0:
            score += 20  # High volume bullish
            sentiment = "Bullish"
        elif volume_ratio > 1.5:
            score += 10
            sentiment = "Bullish"
        elif volume_ratio > 0.8:
            score += 0
            sentiment = "Neutral"
        elif volume_ratio > 0.5:
            score -= 10  # Low volume bearish
            sentiment = "Bearish"
        else:
            score -= 15
            sentiment = "Bearish"
        
        # Adjust for trend
        if volume_trend == "Rising":
            score += 10
        else:
            score -= 5
        
        score = max(0, min(100, score))
        return sentiment, score
    
    def _analyze_price_momentum(self) -> Tuple[str, float]:
        """Analyze recent price momentum"""
        if self.data is None or 'Close' not in self.data.columns:
            return "Neutral", 50
        
        close = self.data['Close']
        
        # Calculate returns over different periods
        ret_5d = ((close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] * 100) if len(close) >= 5 else 0
        ret_20d = ((close.iloc[-1] - close.iloc[-20]) / close.iloc[-20] * 100) if len(close) >= 20 else 0
        ret_60d = ((close.iloc[-1] - close.iloc[-60]) / close.iloc[-60] * 100) if len(close) >= 60 else 0
        
        # Momentum scoring
        score = 50  # Neutral baseline
        
        if ret_5d > 5 and ret_20d > 5:
            score += 25  # Strong uptrend
            sentiment = "Bullish"
        elif ret_5d > 0 and ret_20d > 0:
            score += 15  # Mild uptrend
            sentiment = "Bullish"
        elif ret_5d < -5 and ret_20d < -5:
            score -= 25  # Strong downtrend
            sentiment = "Bearish"
        elif ret_5d < 0 and ret_20d < 0:
            score -= 15  # Mild downtrend
            sentiment = "Bearish"
        else:
            sentiment = "Neutral"
        
        score = max(0, min(100, score))
        return sentiment, score
    
    def _analyze_volatility_expectation(self) -> Tuple[str, float]:
        """Analyze volatility trend (rising = uncertainty = caution)"""
        if self.data is None or 'Close' not in self.data.columns:
            return "Stable", 50
        
        close = self.data['Close']
        
        # Calculate rolling volatility
        returns = close.pct_change()
        vol_20 = returns.tail(20).std() * np.sqrt(252) * 100  # Annualized
        vol_60 = returns.tail(60).std() * np.sqrt(252) * 100
        vol_10 = returns.tail(10).std() * np.sqrt(252) * 100
        
        # Volatility trend
        vol_increasing = vol_10 > vol_20 > vol_60
        vol_decreasing = vol_10 < vol_20 < vol_60
        
        score = 50  # Neutral baseline
        
        if vol_decreasing:
            expectation = "Falling"
            score += 15  # Lower volatility = more bullish
            sentiment = "Bullish"
        elif vol_increasing:
            expectation = "Rising"
            score -= 15  # Rising volatility = caution
            sentiment = "Bearish"
        else:
            expectation = "Stable"
            sentiment = "Neutral"
        
        score = max(0, min(100, score))
        return expectation, score
    
    def generate_signal(self) -> Optional[SentimentSignal]:
        """Generate complete sentiment signal"""
        
        # Fetch data
        if not self.fetch_data():
            # No data - return neutral signal
            return SentimentSignal(
                volume_sentiment="Neutral",
                volume_score=50,
                price_momentum="Neutral",
                momentum_score=50,
                volatility_expectation="Stable",
                volatility_score=50,
                signal="HOLD",
                score=50,
                confidence=30,
                explanation="Insufficient data for sentiment analysis → neutral signal"
            )
        
        # Check for pump-and-dump
        is_pump, pump_msg = self._detect_pump_and_dump()
        
        # Analyze sentiment components
        volume_sentiment, volume_score = self._analyze_volume_sentiment()
        momentum_sentiment, momentum_score = self._analyze_price_momentum()
        volatility_exp, volatility_score = self._analyze_volatility_expectation()
        
        # Cap score if pump detected
        if is_pump:
            volume_score = min(volume_score, 50)
            momentum_score = min(momentum_score, 50)
        
        # Check for signal divergence (conflicting indicators)
        sentiments = [volume_sentiment, momentum_sentiment]
        bearish_count = sentiments.count("Bearish")
        bullish_count = sentiments.count("Bullish")
        
        has_divergence = abs(bearish_count - bullish_count) == 0  # Equal split
        
        # Composite sentiment
        avg_score = (volume_score + momentum_score + volatility_score) / 3
        
        if has_divergence:
            # Conflicting signals reduce confidence
            confidence = 40
            signal = "HOLD"
        elif bullish_count >= 2 and volatility_score >= 50:
            signal = "BUY"
            confidence = 65
        elif bearish_count >= 2 or volatility_score < 40:
            signal = "SELL"
            confidence = 60
        else:
            signal = "HOLD"
            confidence = 50
        
        # Build explanation
        explanation_parts = [
            f"Volume: {volume_sentiment} ({volume_score:.0f})",
            f"Momentum: {momentum_sentiment} ({momentum_score:.0f})",
            f"Volatility: {volatility_exp} ({volatility_score:.0f})"
        ]
        
        if is_pump:
            explanation_parts.append(pump_msg)
        
        if has_divergence:
            explanation_parts.append("⚠️ Divergent signals → confidence reduced")
        
        explanation = " | ".join(explanation_parts)
        
        return SentimentSignal(
            volume_sentiment=volume_sentiment,
            volume_score=volume_score,
            price_momentum=momentum_sentiment,
            momentum_score=momentum_score,
            volatility_expectation=volatility_exp,
            volatility_score=volatility_score,
            signal=signal,
            score=avg_score,
            confidence=confidence,
            explanation=explanation
        )

if __name__ == "__main__":
    # Test
    engine = SentimentAnalysisEngine("RELIANCE.NS")
    signal = engine.generate_signal()
    if signal:
        print(f"Sentiment Signal: {signal.signal} (Score: {signal.score:.1f}, Confidence: {signal.confidence:.0f}%)")
        print(f"Explanation: {signal.explanation}")
    else:
        print("Failed to generate signal")
