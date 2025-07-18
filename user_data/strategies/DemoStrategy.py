from freqtrade.strategy import IStrategy, IntParameter
from pandas import DataFrame
import talib.abstract as ta
import numpy as np
from datetime import datetime, timedelta, timezone
from freqtrade.persistence import Trade
from technical.util import qtpylib

class DemoStrategy(IStrategy):
    """
    Demo strategy implementing basic order types.
    Implements:
    - Regular market/limit orders
    - Stop-loss orders
    - Trailing stop-loss
    - Multiple buy signals using RSI + MACD
    """
    INTERFACE_VERSION = 3

    # Buy hyperspace params:
    buy_rsi = IntParameter(low=10, high=40, default=30, space='buy', optimize=True)
    
    # Minimal ROI designed for the strategy
    minimal_roi = {
        "0": 0.10,  # 10% for quick profits
        "30": 0.05,
        "60": 0.03,
    }

    # Optimal stoploss designed for the strategy
    stoploss = -0.05  # 5% stop loss

    # Trailing stoploss
    trailing_stop = True
    trailing_stop_positive = 0.01  # Trigger 1% above
    trailing_stop_positive_offset = 0.02  # Offset from trigger 2%
    trailing_only_offset_is_reached = True  # Only act once offset is reached

    # Run "populate_indicators()" only for new candle.
    process_only_new_candles = True

    # These values can be overridden in the config.
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 30

    # Optional order type mapping.
    order_types = {
        'entry': 'limit',
        'exit': 'limit',
        'stoploss': 'market',
        'stoploss_on_exchange': True,
        'stoploss_on_exchange_interval': 60,
        'stoploss_on_exchange_limit_ratio': 0.99
    }

    # Optional order time in force.
    order_time_in_force = {
        'entry': 'gtc',
        'exit': 'gtc'
    }

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds several different TA indicators to the given DataFrame
        """
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)

        # MACD
        macd = ta.MACD(dataframe)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']

        # Bollinger Bands
        bollinger = ta.BBANDS(dataframe, timeperiod=20, nbdevup=2.0, nbdevdn=2.0)
        dataframe['bb_lowerband'] = bollinger['lowerband']
        dataframe['bb_middleband'] = bollinger['middleband']
        dataframe['bb_upperband'] = bollinger['upperband']

        # EMA - Exponential Moving Average
        dataframe['ema9'] = ta.EMA(dataframe, timeperiod=9)
        dataframe['ema21'] = ta.EMA(dataframe, timeperiod=21)

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        """
        dataframe.loc[
            (
                # MACD crosses signal upward
                (qtpylib.crossed_above(dataframe['macd'], dataframe['macdsignal'])) &
                # RSI is below buy_rsi
                (dataframe['rsi'] < self.buy_rsi.value) &
                # Price is below BB middle
                (dataframe['close'] < dataframe['bb_middleband']) &
                # Volume is above average
                (dataframe['volume'] > 0)
            ),
            'enter_long'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        """
        dataframe.loc[
            (
                # MACD crosses signal downward
                (qtpylib.crossed_below(dataframe['macd'], dataframe['macdsignal'])) &
                # RSI is above 70
                (dataframe['rsi'] > 70) &
                # Price is above BB middle
                (dataframe['close'] > dataframe['bb_middleband'])
            ),
            'exit_long'] = 1

        return dataframe

    def custom_stoploss(self, pair: str, trade: 'Trade', current_time: datetime,
                       current_rate: float, current_profit: float, **kwargs) -> float:
        """
        Custom stoploss logic, returning the new distance relative to current_rate (as ratio).
        """
        # evaluate highest to lowest, so that highest possible stop is used
        if current_profit > 0.20:
            return 0.05
        elif current_profit > 0.10:
            return 0.03
        elif current_profit > 0.05:
            return 0.02

        # return maximum stoploss value, keeping current stoploss price unchanged
        return -1

    def custom_exit(self, pair: str, trade: 'Trade', current_time: datetime, current_rate: float,
                   current_profit: float, **kwargs) -> bool:
        """
        Custom exit signal logic indicating that specified position should be sold.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()

        # If trade is profitable and MACD is starting to drop
        if current_profit > 0.02 and last_candle['macd'] < last_candle['macdsignal']:
            return True

        return False
