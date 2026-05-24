import yfinance as yf
import pandas as pd
from datetime import datetime


class StockScreener:

    def __init__(self):
        pass

    def get_historical_data(self, symbol, days=180):

        try:

            ticker = yf.Ticker(
                f"{symbol}.NS"
            )

            df = ticker.history(
                period=f"{days}d"
            )

            if df.empty:
                return None

            return df

        except Exception as e:
            print(e)
            return None

    def get_fundamental_data(self, symbol):

        try:

            ticker = yf.Ticker(
                f"{symbol}.NS"
            )

            info = ticker.info

            return {

                "market_cap":
                    info.get(
                        "marketCap",
                        0
                    ),

                "profit_margin":
                    info.get(
                        "profitMargins",
                        0
                    ),

                "debt_to_equity":
                    info.get(
                        "debtToEquity",
                        0
                    )

            }

        except:
            return None

    def calculate_ema(
        self,
        data,
        period
    ):

        return data[
            "Close"
        ].ewm(
            span=period,
            adjust=False
        ).mean()

    def calculate_rsi(
        self,
        data,
        period=14
    ):

        delta = data[
            "Close"
        ].diff()

        gain = (
            delta.where(
                delta > 0,
                0
            )
        ).rolling(
            period
        ).mean()

        loss = (
            -delta.where(
                delta < 0,
                0
            )
        ).rolling(
            period
        ).mean()

        rs = gain / loss

        return 100 - (
            100 / (
                1 + rs
            )
        )

    def calculate_macd(self, data):

        exp1 = data[
            "Close"
        ].ewm(
            span=12,
            adjust=False
        ).mean()

        exp2 = data[
            "Close"
        ].ewm(
            span=26,
            adjust=False
        ).mean()

        macd = exp1 - exp2

        signal = macd.ewm(
            span=9,
            adjust=False
        ).mean()

        return macd, signal

    def calculate_atr(
        self,
        data,
        period=14
    ):

        high_low = (
            data["High"]
            - data["Low"]
        )

        high_close = abs(
            data["High"]
            - data["Close"].shift()
        )

        low_close = abs(
            data["Low"]
            - data["Close"].shift()
        )

        ranges = pd.concat(
            [
                high_low,
                high_close,
                low_close
            ],
            axis=1
        )

        true_range = ranges.max(
            axis=1
        )

        atr = true_range.rolling(
            period
        ).mean()

        return atr

    def technical_analysis(
        self,
        symbol
    ):

        data = self.get_historical_data(symbol)

        if data is None:

            return None

        data["EMA20"] = self.calculate_ema(
            data,
            20
        )

        data["EMA50"] = self.calculate_ema(
            data,
            50
        )

        data["RSI"] = self.calculate_rsi(
            data
        )

        macd, macd_signal = self.calculate_macd(
            data
        )

        data["MACD"] = macd
        data["MACD_SIGNAL"] = macd_signal

        data["ATR"] = self.calculate_atr(
            data
        )

        latest = data.iloc[-1]

        score = 50

        trend = "Neutral"

        if latest["EMA20"] > latest["EMA50"]:

            score += 20
            trend = "Bullish"

        else:

            score -= 20
            trend = "Bearish"

        if latest["RSI"] < 30:

            score += 15

        elif latest["RSI"] > 70:

            score -= 15

        if latest["MACD"] > latest["MACD_SIGNAL"]:

            score += 15

        score = max(
            0,
            min(
                100,
                score
            )
        )

        return {

            "score": round(score),

            "trend": trend,

            "price": round(
                latest["Close"],
                2
            ),

            "atr": round(
                latest["ATR"],
                2
            ),

            "ema20": round(
                latest["EMA20"],
                2
            ),

            "ema50": round(
                latest["EMA50"],
                2
            ),

            "rsi": round(
                latest["RSI"],
                2
            )

        }

    def fundamental_analysis(
        self,
        symbol
    ):

        fundamentals = self.get_fundamental_data(
            symbol
        )

        if not fundamentals:

            return {

                "score": 40,
                "grade": "C"

            }

        score = 50

        if fundamentals[
            "market_cap"
        ] > 100000000000:

            score += 20

        if fundamentals[
            "profit_margin"
        ] > 0.10:

            score += 20

        debt = fundamentals[
            "debt_to_equity"
        ]

        if debt and debt < 100:

            score += 10

        score = max(
            0,
            min(
                100,
                score
            )
        )

        grade = "C"

        if score >= 80:
            grade = "A"

        elif score >= 60:
            grade = "B"

        return {

            "score":
                score,

            "grade":
                grade

        }

    def sentiment_analysis(
        self,
        symbol
    ):

        data = self.get_historical_data(
            symbol,
            30
        )

        if data is None:

            return {
                "score": 50
            }

        returns = (
            data["Close"]
            .pct_change()
            .mean()
        )

        volume_ratio = (

            data["Volume"].iloc[-1]

            /

            data["Volume"].mean()

        )

        score = 50

        if returns > 0:

            score += 20

        if volume_ratio > 1.2:

            score += 10

        return {

            "score":
                max(
                    0,
                    min(
                        100,
                        round(score)
                    )
                )

        }

    def generate_trade_levels(
        self,
        price,
        atr
    ):

        entry = price

        tp1 = price + atr

        tp2 = price + (
            atr * 2
        )

        stop_loss = price - atr

        return {

            "entry":
                round(entry,2),

            "tp1":
                round(tp1,2),

            "tp2":
                round(tp2,2),

            "stop_loss":
                round(stop_loss,2)

        }

    def get_signal(
        self,
        symbol
    ):

        technical = self.technical_analysis(
            symbol
        )

        if not technical:

            return {

                "symbol":
                    symbol,

                "signal":
                    "NO_DATA"

            }

        fundamental = self.fundamental_analysis(
            symbol
        )

        sentiment = self.sentiment_analysis(
            symbol
        )

        final_score = round(

            (
                technical["score"] * 0.5
            )

            +

            (
                fundamental["score"] * 0.3
            )

            +

            (
                sentiment["score"] * 0.2
            )

        )

        signal = "HOLD"

        if final_score >= 70:

            signal = "BUY"

        elif final_score <= 35:

            signal = "SELL"

        levels = self.generate_trade_levels(

            technical["price"],

            technical["atr"]

        )

        return {

            "symbol":
                symbol,

            "signal":
                signal,

            "score":
                final_score,

            "trend":
                technical["trend"],

            "technical_score":
                technical["score"],

            "fundamental_score":
                fundamental["score"],

            "sentiment_score":
                sentiment["score"],

            "fundamental_grade":
                fundamental["grade"],

            "price":
                technical["price"],

            "entry":
                levels["entry"],

            "tp1":
                levels["tp1"],

            "tp2":
                levels["tp2"],

            "stop_loss":
                levels["stop_loss"],

            "explanation": {

                "technical":
                    f"EMA trend is {technical['trend']} with RSI at {technical['rsi']}",

                "fundamental":
                    f"Financial quality grade {fundamental['grade']}",

                "sentiment":
                    f"Sentiment score {sentiment['score']}"

            },

            "last_updated":
                datetime.utcnow().isoformat()

        }

    def scan_portfolio(
        self,
        symbols,
        strategy=None
    ):

        results = []

        for symbol in symbols:

            result = self.get_signal(
                symbol
            )

            results.append(
                result
            )

        return results