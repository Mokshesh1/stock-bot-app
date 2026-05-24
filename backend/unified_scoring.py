from dataclasses import dataclass
from typing import Optional, Dict, Tuple
import logging
from technical_analysis import TechnicalAnalysisEngine, TechnicalSignal
from fundamental_analysis import FundamentalAnalysisEngine, FundamentalSignal
from sentiment_analysis import SentimentAnalysisEngine, SentimentSignal

logger = logging.getLogger(__name__)

@dataclass
class UnifiedSignal:
    """Complete unified signal output"""
    symbol: str
    
    # Pillar scores
    technical_signal: Optional[TechnicalSignal]
    fundamental_signal: Optional[FundamentalSignal]
    sentiment_signal: Optional[SentimentSignal]
    
    # Weighted scores
    technical_score: float  # 0-100
    fundamental_score: float  # 0-100
    sentiment_score: float  # 0-100
    
    # Weights applied
    technical_weight: float
    fundamental_weight: float
    sentiment_weight: float
    
    # Final output
    final_score: float  # 0-100
    final_signal: str   # BUY, SELL, HOLD
    confidence: float   # 0-100
    risk_level: str     # low, medium, high
    
    # Explainability
    technical_explanation: str
    fundamental_explanation: str
    sentiment_explanation: str
    summary_explanation: str

class UnifiedScoringModel:
    """
    Combines Technical (40%), Fundamental (35%), Sentiment (25%) into unified signal
    Edge cases: Weight mismatch → auto-normalize; Extreme disagreement → HOLD; Score saturation → cap at 95
    """
    
    DEFAULT_WEIGHTS = {
        "technical": 0.40,
        "fundamental": 0.35,
        "sentiment": 0.25
    }
    
    def __init__(
        self,
        symbol: str,
        weights: Optional[Dict[str, float]] = None
    ):
        """
        Args:
            symbol: Stock ticker
            weights: Optional custom weights (will auto-normalize if provided)
        """
        self.symbol = symbol
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self._normalize_weights()
    
    def _normalize_weights(self):
        """Normalize weights to sum to 1.0 (handles weight mismatch edge case)"""
        total = sum(self.weights.values())
        if total == 0:
            self.weights = self.DEFAULT_WEIGHTS.copy()
        else:
            for key in self.weights:
                self.weights[key] /= total
        
        logger.info(f"Normalized weights: Tech={self.weights['technical']:.2%}, Fund={self.weights['fundamental']:.2%}, Sent={self.weights['sentiment']:.2%}")
    
    def _assess_disagreement(
        self,
        tech_signal: Optional[TechnicalSignal],
        fund_signal: Optional[FundamentalSignal],
        sent_signal: Optional[SentimentSignal]
    ) -> Tuple[bool, str]:
        """Detect extreme disagreement between pillars"""
        signals = []
        
        if tech_signal:
            signals.append(tech_signal.signal)
        if fund_signal:
            signals.append(fund_signal.signal)
        if sent_signal:
            signals.append(sent_signal.signal)
        
        # Check for max disagreement (e.g., BUY, SELL, HOLD all present)
        unique_signals = set(signals)
        if len(unique_signals) == 3:  # All three signal types present
            return True, "Extreme disagreement (all 3 signal types present)"
        
        # Check for BUY vs SELL disagreement
        if "BUY" in signals and "SELL" in signals:
            return True, "Conflicting BUY/SELL signals"
        
        return False, ""
    
    def _calculate_risk_level(
        self,
        tech_score: float,
        fund_score: float,
        sent_score: float,
        consensus: str
    ) -> str:
        """Assess risk level based on signal confidence and volatility"""
        avg_score = (tech_score + fund_score + sent_score) / 3
        
        # Risk = inverse of consensus confidence
        if consensus == "BUY":
            if avg_score > 75:
                return "low"
            elif avg_score > 60:
                return "medium"
            else:
                return "high"
        elif consensus == "SELL":
            if avg_score < 35:
                return "low"  # Clear downtrend
            elif avg_score < 45:
                return "medium"
            else:
                return "high"  # Uncertain sell
        else:  # HOLD
            return "medium"
    
    def _calculate_confidence(
        self,
        tech_signal: Optional[TechnicalSignal],
        fund_signal: Optional[FundamentalSignal],
        sent_signal: Optional[SentimentSignal],
        has_disagreement: bool
    ) -> float:
        """Calculate overall confidence"""
        confidences = []
        
        if tech_signal:
            confidences.append(tech_signal.confidence)
        if fund_signal:
            confidences.append(fund_signal.confidence)
        if sent_signal:
            confidences.append(sent_signal.confidence)
        
        if not confidences:
            return 30  # Very low confidence if no signals
        
        base_confidence = sum(confidences) / len(confidences)
        
        # Reduce confidence if disagreement detected
        if has_disagreement:
            base_confidence *= 0.6  # 40% penalty
        
        return max(0, min(100, base_confidence))
    
    def generate_signal(self) -> Optional[UnifiedSignal]:
        """Generate complete unified signal"""
        
        # Generate signals from all three engines
        logger.info(f"Generating unified signal for {self.symbol}")
        
        tech_engine = TechnicalAnalysisEngine(self.symbol)
        tech_signal = tech_engine.generate_signal()
        
        fund_engine = FundamentalAnalysisEngine(self.symbol)
        fund_signal = fund_engine.generate_signal()
        
        sent_engine = SentimentAnalysisEngine(self.symbol)
        sent_signal = sent_engine.generate_signal()
        
        # Extract scores (or use neutral if unavailable)
        tech_score = tech_signal.score if tech_signal else 50
        fund_score = fund_signal.score if fund_signal else 50
        sent_score = sent_signal.score if sent_signal else 50
        
        # Check for extreme disagreement
        has_disagreement, disagreement_msg = self._assess_disagreement(
            tech_signal, fund_signal, sent_signal
        )
        
        # Calculate weighted final score
        final_score = (
            tech_score * self.weights['technical'] +
            fund_score * self.weights['fundamental'] +
            sent_score * self.weights['sentiment']
        )
        
        # Cap at 95 (score saturation edge case)
        final_score = min(final_score, 95)
        
        # Determine final signal
        if has_disagreement:
            # Extreme disagreement → force HOLD
            final_signal = "HOLD"
            confidence = self._calculate_confidence(tech_signal, fund_signal, sent_signal, True)
        else:
            # Consensus voting
            buy_signals = sum(1 for s in [tech_signal, fund_signal, sent_signal] if s and s.signal == "BUY")
            sell_signals = sum(1 for s in [tech_signal, fund_signal, sent_signal] if s and s.signal == "SELL")
            
            if buy_signals >= 2:
                final_signal = "BUY"
            elif sell_signals >= 2:
                final_signal = "SELL"
            else:
                final_signal = "HOLD"
            
            confidence = self._calculate_confidence(tech_signal, fund_signal, sent_signal, False)
        
        # Calculate risk level
        risk_level = self._calculate_risk_level(tech_score, fund_score, sent_score, final_signal)
        
        # Build explanations
        tech_explanation = tech_signal.explanation if tech_signal else "No technical data"
        fund_explanation = fund_signal.explanation if fund_signal else "No fundamental data"
        sent_explanation = sent_signal.explanation if sent_signal else "No sentiment data"
        
        # Summary explanation
        summary_parts = []
        if has_disagreement:
            summary_parts.append(f"⚠️ {disagreement_msg} → Signal downgraded to HOLD")
        
        summary_parts.append(f"Unified Score: {final_score:.1f}/100")
        summary_parts.append(f"Signal: {final_signal} (Confidence: {confidence:.0f}%)")
        summary_parts.append(f"Risk: {risk_level.upper()}")
        
        # Contribution breakdown
        summary_parts.append(
            f"Pillar Scores: Tech {tech_score:.0f} | Fund {fund_score:.0f} | Sent {sent_score:.0f}"
        )
        
        summary_explanation = " | ".join(summary_parts)
        
        return UnifiedSignal(
            symbol=self.symbol,
            technical_signal=tech_signal,
            fundamental_signal=fund_signal,
            sentiment_signal=sent_signal,
            technical_score=tech_score,
            fundamental_score=fund_score,
            sentiment_score=sent_score,
            technical_weight=self.weights['technical'],
            fundamental_weight=self.weights['fundamental'],
            sentiment_weight=self.weights['sentiment'],
            final_score=final_score,
            final_signal=final_signal,
            confidence=confidence,
            risk_level=risk_level,
            technical_explanation=tech_explanation,
            fundamental_explanation=fund_explanation,
            sentiment_explanation=sent_explanation,
            summary_explanation=summary_explanation
        )

if __name__ == "__main__":
    # Test
    model = UnifiedScoringModel("RELIANCE.NS")
    signal = model.generate_signal()
    if signal:
        print(f"Final Signal: {signal.final_signal}")
        print(f"Score: {signal.final_score:.1f}/100 (Confidence: {signal.confidence:.0f}%)")
        print(f"Risk: {signal.risk_level}")
        print(f"\nTechnical: {signal.technical_explanation}")
        print(f"Fundamental: {signal.fundamental_explanation}")
        print(f"Sentiment: {signal.sentiment_explanation}")
        print(f"\nSummary: {signal.summary_explanation}")
    else:
        print("Failed to generate signal")
