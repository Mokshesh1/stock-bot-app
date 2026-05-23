from kiteconnect import KiteConnect
import os

class ZerodhaClient:
    def __init__(self, api_key, api_secret, user_id, password, totp):
        """
        Initialize Zerodha client
        Get api_key and api_secret from https://kite.trade/
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.user_id = user_id
        self.password = password
        self.totp = totp
        self.kite = None
        self.authenticate()

    def authenticate(self):
        """Login to Zerodha"""
        try:
            self.kite = KiteConnect(api_key=self.api_key)
            # In real implementation, use the login URL and TOTP
            print("Zerodha client initialized")
        except Exception as e:
            print(f"Authentication error:{e}")

    def get_stock_price(self, symbol):
        """Get current price of a stock"""
        try:
            # Format: NSE:RELIANCE for NSE stocks
            if not symbol.startswith('NSE:'):
                symbol = f'NSE:{symbol}'

            quote = self.kite.quote([symbol])
            price = quote[symbol]['last_price']
            return price
        except Exception as e:
            print(f"Error getting price:{e}")
            return None

    def place_order(self, symbol, quantity, price, order_type='LIMIT', transaction_type='BUY'):
        """Place an order"""
        try:
            order_id = self.kite.place_order(
                variety='regular',
                exchange='NSE',
                tradingsymbol=symbol,
                transaction_type=transaction_type,
                quantity=quantity,
                price=price,
                order_type=order_type
            )
            return order_id
        except Exception as e:
            print(f"Error placing order:{e}")
            return None

    def get_order_status(self, order_id):
        """Get status of an order"""
        try:
            orders = self.kite.orders()
            for order in orders:
                if order['order_id'] == order_id:
                    return order
            return None
        except Exception as e:
            print(f"Error getting order:{e}")
            return None