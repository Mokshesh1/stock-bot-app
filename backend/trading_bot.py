from datetime import datetime, timedelta
from models import db, Trade
from zerodha_integration import ZerodhaClient
from screener import StockScreener

class TradingBot:
    def __init__(self, user, zerodha_client, screener):
        self.user = user
        self.zerodha = zerodha_client
        self.screener = screener
        self.is_running = False

    def start(self):
        """Start the trading bot"""
        self.is_running = True
        print(f"Bot started for user:{self.user.name}")

    def stop(self):
        """Stop the trading bot"""
        self.is_running = False
        print(f"Bot stopped for user:{self.user.name}")

    def execute_ema_crossover_strategy(self, symbol, quantity, profit_target_pct=2, stop_loss_pct=1):
        """
        Execute EMA crossover trading strategy
        1. Get EMA signal
        2. If BUY signal, place order
        3. Track for exit
        """
        try:
            # Get signal
            signal_result = self.screener.ema_crossover_signal(symbol)
            signal = signal_result.get('signal')
            current_price = signal_result.get('price')

            if signal == 'BUY':
                # Place BUY order
                order_id = self.zerodha.place_order(
                    symbol=symbol,
                    quantity=quantity,
                    price=current_price,
                    transaction_type='BUY'
                )

                if order_id:
                    # Create trade record
                    trade = Trade(
                        user_id=self.user.id,
                        symbol=symbol,
                        entry_price=current_price,
                        quantity=quantity,
                        strategy='EMA_CROSSOVER',
                        status='open'
                    )
                    db.session.add(trade)
                    db.session.commit()

                    # Calculate exit prices
                    profit_target = current_price * (1 + profit_target_pct/100)
                    stop_loss = current_price * (1 - stop_loss_pct/100)

                    return {
                        'success': True,
                        'order_id': order_id,
                        'symbol': symbol,
                        'entry_price': current_price,
                        'profit_target': profit_target,
                        'stop_loss': stop_loss
                    }

            return {'success': False, 'signal': signal, 'message': 'No BUY signal'}

        except Exception as e:
            return {'success': False, 'message': str(e)}

    def execute_rsi_strategy(self, symbol, quantity, profit_target_pct=2, stop_loss_pct=1):
        """Execute RSI-based trading strategy"""
        try:
            signal_result = self.screener.rsi_signal(symbol)
            signal = signal_result.get('signal')
            current_price = signal_result.get('price')

            if signal == 'BUY':
                order_id = self.zerodha.place_order(
                    symbol=symbol,
                    quantity=quantity,
                    price=current_price,
                    transaction_type='BUY'
                )

                if order_id:
                    trade = Trade(
                        user_id=self.user.id,
                        symbol=symbol,
                        entry_price=current_price,
                        quantity=quantity,
                        strategy='RSI',
                        status='open'
                    )
                    db.session.add(trade)
                    db.session.commit()

                    return {
                        'success': True,
                        'order_id': order_id,
                        'symbol': symbol,
                        'entry_price': current_price
                    }

            return {'success': False, 'signal': signal}

        except Exception as e:
            return {'success': False, 'message': str(e)}

    def close_trade(self, trade_id, exit_price):
        """Close an open trade"""
        try:
            trade = Trade.query.get(trade_id)
            if not trade or trade.user_id != self.user.id:
                return {'success': False, 'message': 'Trade not found'}

            # Place SELL order
            order_id = self.zerodha.place_order(
                symbol=trade.symbol,
                quantity=trade.quantity,
                price=exit_price,
                transaction_type='SELL'
            )

            if order_id:
                trade.exit_price = exit_price
                trade.exit_time = datetime.utcnow()
                trade.profit_loss = (exit_price - trade.entry_price) * trade.quantity
                trade.status = 'closed'

                db.session.commit()

                return {
                    'success': True,
                    'trade_id': trade_id,
                    'profit_loss': trade.profit_loss
                }

            return {'success': False, 'message': 'Failed to place exit order'}

        except Exception as e:
            return {'success': False, 'message': str(e)}