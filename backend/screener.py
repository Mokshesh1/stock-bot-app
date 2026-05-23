import pandas as pd
import requests
from datetime import datetime, timedelta

class StockScreener:
    def __init__(self):
        """Initialize screener with technical indicators"""
        pass

    def get_historical_data(self, symbol, days=100):
        """
        Get historical data for a stock
        Using yfinance API (free)
        """
        try:
            import yfinance as yf

            # Download data
            ticker = yf.Ticker(f'{symbol}.NS')  # .NS for NSE
            df = ticker.history(period=f'{days}d')

            return df
        except Exception as e:
            print(f"Error getting data:{e}")
            return None

    def calculate_ema(self, data, period):
        """Calculate Exponential Moving Average"""
        return data['Close'].ewm(span=period, adjust=False).mean()

    def calculate_rsi(self, data, period=14):
        """Calculate Relative Strength Index"""
        delta = data['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_macd(self, data):
        """Calculate MACD"""
        exp1 = data['Close'].ewm(span=12, adjust=False).mean()
        exp2 = data['Close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        histogram = macd - signal
        return macd, signal, histogram

    def ema_crossover_signal(self, symbol):
        """
        EMA Crossover Strategy
        BUY: When EMA12 crosses above EMA26
        SELL: When EMA12 crosses below EMA26
        """
        try:
            data = self.get_historical_data(symbol, days=100)
            if data is None:
                return {'symbol': symbol, 'signal': 'NO_DATA'}

            # Calculate EMAs
            data['EMA_12'] = self.calculate_ema(data, 12)
            data['EMA_26'] = self.calculate_ema(data, 26)

            # Get latest values
            latest_ema12 = data['EMA_12'].iloc[-1]
            latest_ema26 = data['EMA_26'].iloc[-1]
            prev_ema12 = data['EMA_12'].iloc[-2]
            prev_ema26 = data['EMA_26'].iloc[-2]

            # Determine signal
            signal = 'HOLD'
            if prev_ema12 <= prev_ema26 and latest_ema12 > latest_ema26:
                signal = 'BUY'
            elif prev_ema12 >= prev_ema26 and latest_ema12 < latest_ema26:
                signal = 'SELL'

            return {
                'symbol': symbol,
                'signal': signal,
                'ema_12': latest_ema12,
                'ema_26': latest_ema26,
                'price': data['Close'].iloc[-1]
            }

        except Exception as e:
            return {'symbol': symbol, 'signal': 'ERROR', 'error': str(e)}

    def rsi_signal(self, symbol, oversold=30, overbought=70):
        """
        RSI Strategy
        BUY: When RSI < 30 (oversold)
        SELL: When RSI > 70 (overbought)
        """
        try:
            data = self.get_historical_data(symbol, days=100)
            if data is None:
                return {'symbol': symbol, 'signal': 'NO_DATA'}

            # Calculate RSI
            rsi = self.calculate_rsi(data)

            latest_rsi = rsi.iloc[-1]

            signal = 'HOLD'
            if latest_rsi < oversold:
                signal = 'BUY'
            elif latest_rsi > overbought:
                signal = 'SELL'

            return {
                'symbol': symbol,
                'signal': signal,
                'rsi': latest_rsi,
                'price': data['Close'].iloc[-1]
            }

        except Exception as e:
            return {'symbol': symbol, 'signal': 'ERROR', 'error': str(e)}

    def scan_portfolio(self, symbols, strategy='ema_crossover'):
        """Scan multiple stocks and return signals"""
        results = []

        for symbol in symbols:
            if strategy == 'ema_crossover':
                signal = self.ema_crossover_signal(symbol)
            elif strategy == 'rsi':
                signal = self.rsi_signal(symbol)
            else:
                signal = {'symbol': symbol, 'signal': 'UNKNOWN'}

            results.append(signal)

        return results