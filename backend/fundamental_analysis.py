import yfinance as yf
from typing import Optional, Tuple
from dataclasses import dataclass
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

@dataclass
class FundamentalSignal:
    """Output of fundamental analysis"""
    market_cap: Optional[float]
    pe_ratio: Optional[float]
    profit_margin: Optional[float]
    debt_to_equity: Optional[float]
    roe: Optional[float]
    revenue_growth: Optional[float]
    
    # Scores
    profitability_score: float  # 0-100
    valuation_score: float      # 0-100
    financial_health_score: float  # 0-100
    
    grade: str  # A, B, C
    signal: str  # BUY, SELL, HOLD
    score: float  # 0-100
    confidence: float  # 0-100
    explanation: str

class FundamentalAnalysisEngine:
    """
    Analyzes fundamental financial metrics: Market cap, P/E, profitability, debt
    Edge cases: Missing data → cap score at 40; IPO stocks → neutral baseline; Invalid → exclude
    """
    
    def __init__(self, symbol: str):
        """
        Args:
            symbol: Stock ticker (e.g., 'RELIANCE.NS')
        """
        self.symbol = symbol
        self.ticker = None
        self.info = None
    
    def fetch_data(self) -> bool:
        """Fetch fundamental data from yfinance"""
        try:
            self.ticker = yf.Ticker(self.symbol)
            self.info = self.ticker.info
            
            # Validate minimum data availability
            if not self.info or self.info.get('symbol') is None:
                logger.warning(f"No fundamental data for {self.symbol}")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Failed to fetch fundamental data for {self.symbol}: {e}")
            return False
    
    def _get_safe_value(self, key: str, default=None):
        """Safely extract value from info dict"""
        if not self.info:
            return default
        return self.info.get(key, default)
    
    def _is_ipo_stock(self) -> bool:
        """Check if stock is recently IPO'd"""
        try:
            ipo_date = self.info.get('ipoDate')
            if not ipo_date:
                return False
            
            # If IPO date is within last 6 months, consider it IPO
            days_since_ipo = (datetime.now() - datetime.fromtimestamp(ipo_date)).days
            return days_since_ipo < 180
        except:
            return False
    
    def _score_profitability(self) -> Tuple[float, str]:
        """Score profitability (0-100)"""
        profit_margin = self._get_safe_value('profitMargins')
        roe = self._get_safe_value('returnOnEquity')
        net_income = self._get_safe_value('netIncomeToCommon')
        
        # Handle missing data
        if profit_margin is None and roe is None and net_income is None:
            return 40, "Missing profitability data"
        
        score = 50  # Neutral baseline
        
        # Profit margin scoring (ideal > 10% for healthy companies)
        if profit_margin is not None:
            if profit_margin > 0.15:
                score += 20
            elif profit_margin > 0.10:
                score += 15
            elif profit_margin > 0.05:
                score += 10
            elif profit_margin > 0:
                score += 5
            else:
                score -= 20  # Negative margins are bad
        
        # ROE scoring (ideal > 15% indicates efficient use of capital)
        if roe is not None:
            if roe > 0.20:
                score += 20
            elif roe > 0.15:
                score += 15
            elif roe > 0.10:
                score += 10
            elif roe > 0.05:
                score += 5
            else:
                score -= 10
        
        score = max(0, min(100, score))
        return score, "Profitability assessed"
    
    def _score_valuation(self) -> Tuple[float, str]:
        """Score valuation attractiveness (0-100)"""
        pe_ratio = self._get_safe_value('trailingPE')
        pb_ratio = self._get_safe_value('priceToBook')
        peg_ratio = self._get_safe_value('pegRatio')
        
        # Handle missing data
        if pe_ratio is None and pb_ratio is None:
            return 40, "Missing valuation data"
        
        score = 50  # Neutral baseline
        
        # P/E scoring (lower is better, but must be positive)
        # For NSE stocks, reasonable P/E is 15-25
        if pe_ratio and pe_ratio > 0:
            if pe_ratio < 15:
                score += 20  # Undervalued
            elif pe_ratio < 20:
                score += 10  # Fair value
            elif pe_ratio < 30:
                score += 5   # Slightly expensive
            else:
                score -= 10  # Overvalued
        elif pe_ratio and pe_ratio <= 0:
            score -= 15  # Negative earnings
        
        # P/B scoring (lower is better)
        if pb_ratio and pb_ratio > 0:
            if pb_ratio < 1.0:
                score += 15  # Trading below book
            elif pb_ratio < 2.0:
                score += 10  # Fair valuation
            elif pb_ratio < 3.0:
                score += 5
            else:
                score -= 10  # Expensive
        
        score = max(0, min(100, score))
        return score, "Valuation assessed"
    
    def _score_financial_health(self) -> Tuple[float, str]:
        """Score financial health and solvency (0-100)"""
        total_debt = self._get_safe_value('totalDebt')
        total_equity = self._get_safe_value('totalEquity')
        current_ratio = self._get_safe_value('currentRatio')
        quick_ratio = self._get_safe_value('quickRatio')
        
        # Handle missing data
        if all(x is None for x in [total_debt, total_equity, current_ratio, quick_ratio]):
            return 40, "Missing health data"
        
        score = 50  # Neutral baseline
        
        # Debt-to-equity scoring (lower is better)
        if total_debt is not None and total_equity is not None and total_equity != 0:
            de_ratio = total_debt / total_equity
            if de_ratio < 0.5:
                score += 20  # Healthy
            elif de_ratio < 1.0:
                score += 15  # Acceptable
            elif de_ratio < 1.5:
                score += 5   # Moderate risk
            else:
                score -= 15  # High leverage
        
        # Current ratio scoring (ideal 1.5-3.0)
        if current_ratio is not None:
            if 1.5 <= current_ratio <= 3.0:
                score += 15  # Good liquidity
            elif current_ratio > 1.0:
                score += 10  # Acceptable
            elif current_ratio > 0.5:
                score += 5   # Risky
            else:
                score -= 20  # Critical
        
        score = max(0, min(100, score))
        return score, "Financial health assessed"
    
    def generate_signal(self) -> Optional[FundamentalSignal]:
        """Generate complete fundamental signal"""
        
        # Fetch data
        if not self.fetch_data():
            return None
        
        # Check for IPO
        is_ipo = self._is_ipo_stock()
        if is_ipo:
            logger.info(f"{self.symbol} is a recent IPO, applying neutral baseline")
        
        # Extract metrics
        market_cap = self._get_safe_value('marketCap')
        pe_ratio = self._get_safe_value('trailingPE')
        profit_margin = self._get_safe_value('profitMargins')
        debt_to_equity = None
        total_debt = self._get_safe_value('totalDebt')
        total_equity = self._get_safe_value('totalEquity')
        if total_debt is not None and total_equity is not None and total_equity != 0:
            debt_to_equity = total_debt / total_equity
        roe = self._get_safe_value('returnOnEquity')
        revenue_growth = self._get_safe_value('revenueGrowth')
        
        # Score components
        prof_score, prof_msg = self._score_profitability()
        val_score, val_msg = self._score_valuation()
        health_score, health_msg = self._score_financial_health()
        
        # Adjust for IPO (neutral baseline)
        if is_ipo:
            prof_score = 50
            val_score = 50
            health_score = 50
        
        # Assign grade based on average score
        avg_score = (prof_score + val_score + health_score) / 3
        if avg_score >= 70:
            grade = "A"
        elif avg_score >= 50:
            grade = "B"
        else:
            grade = "C"
        
        # Determine signal
        if grade == "A":
            signal = "BUY"
            confidence = 75
        elif grade == "B":
            signal = "HOLD"
            confidence = 55
        else:
            signal = "SELL"
            confidence = 60
        
        # Calculate final score
        score = max(0, min(100, avg_score))
        
        # Build explanation
        explanation_parts = [
            f"Grade: {grade}",
            f"Profitability: {prof_score:.0f} | Valuation: {val_score:.0f} | Health: {health_score:.0f}"
        ]
        
        if is_ipo:
            explanation_parts.append("⚠️ Recent IPO - neutral assessment applied")
        
        if market_cap:
            market_cap_b = market_cap / 1e9
            explanation_parts.append(f"Market Cap: ${market_cap_b:.1f}B")
        
        if pe_ratio and pe_ratio > 0:
            explanation_parts.append(f"P/E: {pe_ratio:.1f}x")
        
        explanation = " | ".join(explanation_parts)
        
        return FundamentalSignal(
            market_cap=market_cap,
            pe_ratio=pe_ratio,
            profit_margin=profit_margin,
            debt_to_equity=debt_to_equity,
            roe=roe,
            revenue_growth=revenue_growth,
            profitability_score=prof_score,
            valuation_score=val_score,
            financial_health_score=health_score,
            grade=grade,
            signal=signal,
            score=score,
            confidence=confidence,
            explanation=explanation
        )

if __name__ == "__main__":
    # Test
    engine = FundamentalAnalysisEngine("RELIANCE.NS")
    signal = engine.generate_signal()
    if signal:
        print(f"Grade: {signal.grade} | Signal: {signal.signal} (Score: {signal.score:.1f})")
        print(f"Explanation: {signal.explanation}")
    else:
        print("Failed to generate signal")
