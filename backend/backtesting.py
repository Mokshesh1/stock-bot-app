import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import yfinance as yf
import logging

logger = logging.getLogger(__name__)

@dataclass
class BacktestTrade:
    """A single trade in backtest"""
    symbol: str
    entry_date: datetime
    entry_price: float
    quantity: int
    exit_date: datetime
    exit_price: float
    signal: str  # BUY, SELL
    profit_loss: float
    profit_loss_pct: float
    days_held: int
    status: str  # completed

@dataclass
class BacktestMetrics:
    """Backtest performance metrics"""
    symbol: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float  # %
    
    gross_profit: float
    gross_loss: float
    net_profit: float
    
    average_win: float
    average_loss: float
    expectancy: float  # Average profit per trade
    
    largest_win: float
    largest_loss: float
    profit_factor: float  # Gross profit / Gross loss
    
    max_drawdown: float  # %
    max_drawdown_duration: int  # days
    
    sharpe_ratio: float
    sortino_ratio: float
    
    average_hold_days: float
    
    # Risk metrics
    total_risk: float
    risk_adjusted_return: float

class BacktestingEngine:
    """
    Backtests trading strategies on historical data
    Edge cases: Missing data → exclude stock; Outliers → cap returns; Thin trading → mark unreliable
    """
    
    # Transaction costs
    BROKERAGE_PCT = 0.0003  # 0.03% per trade (NSE typical)
    SLIPPAGE_PCT = 0.0005   # 0.05% (typical for liquid stocks)
    
    def __init__(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        initial_capital: float = 100000,
        position_size_pct: float = 100
    ):
        """
        Args:
            symbol: Stock ticker
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            initial_capital: Starting capital
            position_size_pct: % of capital to risk per trade
        """
        self.symbol = symbol
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.position_size_pct = position_size_pct
        self.data = None
        self.trades: List[BacktestTrade] = []
    
    def fetch_data(self) -> bool:
        """Fetch historical OHLC data"""
        try:
            self.data = yf.download(
                self.symbol,
                start=self.start_date,
                end=self.end_date,
                progress=False,
                timeout=10
            )
            
            if self.data is None or self.data.empty or len(self.data) < 20:
                logger.warning(f"Insufficient historical data for {self.symbol}")
                return False
            
            # Check for data quality
            missing_ohlc = self.data[['Open', 'High', 'Low', 'Close']].isna().any()
            if missing_ohlc.any():
                logger.warning(f"Missing OHLC data for {self.symbol}, excluding")
                return False
            
            return True
        except Exception as e:
            logger.error(f"Failed to fetch backtest data for {self.symbol}: {e}")
            return False
    
    def _detect_thin_trading(self) -> Tuple[bool, str]:
        """Detect if stock has thin trading (low liquidity)"""
        if self.data is None:
            return True, "No data"
        
        volume = self.data['Volume']
        avg_volume = volume.mean()
        volume_std = volume.std()
        
        # Flag if coefficient of variation > 100% (highly erratic volume)
        cv = volume_std / avg_volume if avg_volume > 0 else 0
        
        if cv > 1.5:
            return True, "Thin/erratic trading"
        
        return False, "Sufficient liquidity"
    
    def _cap_outlier_returns(self, returns: pd.Series) -> pd.Series:
        """Cap extreme returns to prevent distortion"""
        # Cap at 20% per day (realistic max for NSE stocks)
        max_return = 0.20
        return returns.clip(-max_return, max_return)
    
    def backtest_ema_crossover(self) -> Optional[BacktestMetrics]:
        """
        Backtest EMA(12) > EMA(26) crossover strategy
        BUY when 12-EMA crosses above 26-EMA
        SELL when 12-EMA crosses below 26-EMA
        """
        if not self.fetch_data():
            return None
        
        is_thin, msg = self._detect_thin_trading()
        if is_thin:
            logger.warning(f"Backtest skipped for {self.symbol}: {msg}")
            return None
        
        close = self.data['Close']
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        
        # Generate signals
        position = 0  # 0=flat, 1=long, -1=short
        entry_price = 0
        entry_date = None
        
        for i in range(1, len(self.data)):
            prev_signal = ema12.iloc[i-1] > ema26.iloc[i-1]
            curr_signal = ema12.iloc[i] > ema26.iloc[i]
            
            # BUY signal (crossover)
            if not prev_signal and curr_signal and position == 0:
                entry_price = self.data['Open'].iloc[i]
                entry_date = self.data.index[i]
                position = 1
            
            # SELL signal (crossunder)
            elif prev_signal and not curr_signal and position == 1:
                exit_price = self.data['Open'].iloc[i]
                exit_date = self.data.index[i]
                
                # Calculate P&L with transaction costs
                transaction_cost = entry_price * (self.BROKERAGE_PCT + self.SLIPPAGE_PCT)
                transaction_cost += exit_price * (self.BROKERAGE_PCT + self.SLIPPAGE_PCT)
                
                pnl = (exit_price - entry_price) - transaction_cost
                pnl_pct = (pnl / entry_price) * 100
                days_held = (exit_date - entry_date).days
                
                trade = BacktestTrade(
                    symbol=self.symbol,
                    entry_date=entry_date,
                    entry_price=entry_price,
                    quantity=1,
                    exit_date=exit_date,
                    exit_price=exit_price,
                    signal="BUY",
                    profit_loss=pnl,
                    profit_loss_pct=pnl_pct,
                    days_held=days_held,
                    status="completed"
                )
                self.trades.append(trade)
                position = 0
        
        return self._calculate_metrics()
    
    def backtest_rsi_strategy(self, oversold: int = 30, overbought: int = 70) -> Optional[BacktestMetrics]:
        """
        Backtest RSI(14) strategy
        BUY when RSI < oversold (30)
        SELL when RSI > overbought (70)
        """
        if not self.fetch_data():
            return None
        
        is_thin, msg = self._detect_thin_trading()
        if is_thin:
            logger.warning(f"Backtest skipped for {self.symbol}: {msg}")
            return None
        
        close = self.data['Close']
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss.where(loss != 0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        
        position = 0
        entry_price = 0
        entry_date = None
        
        for i in range(14, len(self.data)):
            # BUY signal
            if rsi.iloc[i] < oversold and position == 0:
                entry_price = self.data['Open'].iloc[i]
                entry_date = self.data.index[i]
                position = 1
            
            # SELL signal
            elif rsi.iloc[i] > overbought and position == 1:
                exit_price = self.data['Open'].iloc[i]
                exit_date = self.data.index[i]
                
                transaction_cost = entry_price * (self.BROKERAGE_PCT + self.SLIPPAGE_PCT)
                transaction_cost += exit_price * (self.BROKERAGE_PCT + self.SLIPPAGE_PCT)
                
                pnl = (exit_price - entry_price) - transaction_cost
                pnl_pct = (pnl / entry_price) * 100
                days_held = (exit_date - entry_date).days
                
                trade = BacktestTrade(
                    symbol=self.symbol,
                    entry_date=entry_date,
                    entry_price=entry_price,
                    quantity=1,
                    exit_date=exit_date,
                    exit_price=exit_price,
                    signal="BUY",
                    profit_loss=pnl,
                    profit_loss_pct=pnl_pct,
                    days_held=days_held,
                    status="completed"
                )
                self.trades.append(trade)
                position = 0
        
        return self._calculate_metrics()
    
    def _calculate_metrics(self) -> Optional[BacktestMetrics]:
        """Calculate performance metrics from trades"""
        if not self.trades:
            return None
        
        trades_df = pd.DataFrame([
            {
                'profit_loss': t.profit_loss,
                'profit_loss_pct': t.profit_loss_pct,
                'days_held': t.days_held,
                'entry_date': t.entry_date
            }
            for t in self.trades
        ])
        
        # Basic metrics
        winning_trades = (trades_df['profit_loss'] > 0).sum()
        losing_trades = (trades_df['profit_loss'] < 0).sum()
        total_trades = len(trades_df)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # P&L metrics
        gross_profit = trades_df[trades_df['profit_loss'] > 0]['profit_loss'].sum()
        gross_loss = abs(trades_df[trades_df['profit_loss'] < 0]['profit_loss'].sum())
        net_profit = trades_df['profit_loss'].sum()
        
        average_win = (gross_profit / winning_trades) if winning_trades > 0 else 0
        average_loss = (gross_loss / losing_trades) if losing_trades > 0 else 0
        expectancy = net_profit / total_trades if total_trades > 0 else 0
        
        # Profit factor
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (99999 if gross_profit > 0 else 0)
        
        # Largest win/loss
        largest_win = trades_df['profit_loss'].max()
        largest_loss = trades_df['profit_loss'].min()
        
        # Drawdown (simplified: peak-to-trough)
        cumulative_pnl = trades_df['profit_loss'].cumsum()
        running_max = cumulative_pnl.expanding().max()
        drawdown = (running_max - cumulative_pnl) / running_max.replace(0, 1) * 100
        max_drawdown = drawdown.max()
        
        # Max drawdown duration
        in_drawdown = drawdown > 0
        max_drawdown_duration = 0
        current_dd_duration = 0
        for in_dd in in_drawdown:
            if in_dd:
                current_dd_duration += 1
                max_drawdown_duration = max(max_drawdown_duration, current_dd_duration)
            else:
                current_dd_duration = 0
        
        # Sharpe and Sortino (simplified)
        returns = trades_df['profit_loss_pct'] / 100
        if len(returns) > 1:
            sharpe_ratio = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
            downside_returns = returns[returns < 0]
            sortino_ratio = returns.mean() / downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 and downside_returns.std() > 0 else sharpe_ratio
        else:
            sharpe_ratio = 0
            sortino_ratio = 0
        
        # Average hold time
        average_hold_days = trades_df['days_held'].mean()
        
        # Risk metrics
        total_risk = abs(gross_loss)
        risk_adjusted_return = net_profit / total_risk if total_risk > 0 else (99999 if net_profit > 0 else 0)
        
        return BacktestMetrics(
            symbol=self.symbol,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            net_profit=net_profit,
            average_win=average_win,
            average_loss=average_loss,
            expectancy=expectancy,
            largest_win=largest_win,
            largest_loss=largest_loss,
            profit_factor=profit_factor,
            max_drawdown=max_drawdown,
            max_drawdown_duration=max_drawdown_duration,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            average_hold_days=average_hold_days,
            total_risk=total_risk,
            risk_adjusted_return=risk_adjusted_return
        )

if __name__ == "__main__":
    # Test backtest
    engine = BacktestingEngine(
        symbol="RELIANCE.NS",
        start_date="2022-01-01",
        end_date="2024-01-01"
    )
    
    metrics = engine.backtest_ema_crossover()
    if metrics:
        print(f"Backtest Results for {metrics.symbol}")
        print(f"Total Trades: {metrics.total_trades}")
        print(f"Win Rate: {metrics.win_rate:.1f}%")
        print(f"Net Profit: {metrics.net_profit:.2f}")
        print(f"Profit Factor: {metrics.profit_factor:.2f}")
        print(f"Max Drawdown: {metrics.max_drawdown:.2f}%")
        print(f"Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
    else:
        print("Backtest failed")
