from freqtrade.strategy import IStrategy
from freqtrade.persistence import Trade
from pandas import DataFrame
import talib.abstract as ta
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class SampleStrategy(IStrategy):
    timeframe = '1m'
    minimal_roi = {
        "0": 100  # Set very high to prevent ROI from closing trades
    }
    stoploss = -0.99  # Set very low to prevent actual stoploss
    trailing_stop = False
    process_only_new_candles = True
    use_exit_signal = True  # We'll use exit signals for our virtual stop loss
    exit_profit_only = False
    ignore_roi_if_entry_signal = True
    order_types = {
        'entry': 'market',
        'exit': 'market',
        'stoploss': 'market',
        'stoploss_on_exchange': False
    }

    # Plot config to show EMAs, Swing Lows, and Virtual Stop Loss in FreqUI
    plot_config = {
        'main_plot': {
            'ema_7': {'color': 'blue'},
            'ema_25': {'color': 'green'},
            'ema_50': {'color': 'yellow'},
            'ema_99': {'color': 'orange'},
            'ema_200': {'color': 'red'},
            'swing_low': {
                'color': 'purple',
                'type': 'line',
                'width': 2
            },
            'entry_swing_low': {
                'color': 'pink',
                'type': 'line',
                'width': 3
            },
            'virtual_stop_line': {
                'color': '#ff0000',
                'type': 'scatter',
                'plotly': {
                    'mode': 'lines',
                    'line': {
                        'width': 3,
                        'dash': 'dash'
                    },
                    'fill': 'none'
                }
            }
        },
        'subplots': {}
    }

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Calculate all EMAs
        dataframe['ema_7'] = ta.EMA(dataframe, timeperiod=7)
        dataframe['ema_25'] = ta.EMA(dataframe, timeperiod=25)
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema_99'] = ta.EMA(dataframe, timeperiod=99)
        dataframe['ema_200'] = ta.EMA(dataframe, timeperiod=200)
        
        # Calculate swing lows (improved version)
        window = 5
        dataframe['min_low'] = dataframe['low'].rolling(window=window).min()
        dataframe['prev_min_low'] = dataframe['min_low'].shift(1)
        
        # Mark swing lows where current low is the lowest in the window
        dataframe['swing_low'] = dataframe.apply(
            lambda row: row['low'] if row['low'] == row['min_low'] and row['low'] < row['prev_min_low']
            else row['prev_min_low'],
            axis=1
        )
        
        # Initialize columns
        dataframe['entry_swing_low'] = 0.0
        dataframe['virtual_stop_line'] = np.nan  # Initialize as NaN to avoid 0 values
        
        # For each row, if there's an entry signal, store the most recent swing low
        last_valid_swing = None
        current_virtual_stop = None
        
        for i in range(len(dataframe)):
            if dataframe.iloc[i]['swing_low'] != dataframe.iloc[i]['prev_min_low']:
                last_valid_swing = dataframe.iloc[i]['swing_low']
            
            # If we have an entry signal, set both the entry swing low and virtual stop
            if dataframe.iloc[i].get('enter_long', 0) == 1 and last_valid_swing is not None:
                dataframe.at[i, 'entry_swing_low'] = last_valid_swing
                current_virtual_stop = last_valid_swing
            
            # If we have an active virtual stop, plot it
            if current_virtual_stop is not None:
                dataframe.at[i, 'virtual_stop_line'] = current_virtual_stop
            
            # If we have an exit signal, clear the virtual stop
            if dataframe.iloc[i].get('exit_long', 0) == 1:
                current_virtual_stop = None
        
        # Forward fill the entry_swing_low
        dataframe['entry_swing_low'] = dataframe['entry_swing_low'].replace(0.0, np.nan).fillna(method='ffill')
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Enter when price is above EMA 25 and trading volume exists"""
        dataframe.loc[
            (
                (dataframe['close'] > dataframe['ema_25']) &  # Price above EMA 25
                (dataframe['volume'] > 0)  # Make sure volume exists
            ),
            'enter_long'
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Exit signals based on technical conditions
        """
        dataframe.loc[
            (
                (dataframe['close'] < dataframe['ema_25']) |  # Price below EMA 25
                (
                    dataframe['virtual_stop_line'].notnull() &  # We have an active virtual stop
                    (dataframe['close'] < dataframe['virtual_stop_line'])  # Price below virtual stop
                )
            ),
            'exit_long'
        ] = 1
        
        return dataframe

    def custom_exit(self, pair: str, trade: Trade, current_time: datetime, current_rate: float,
                   current_profit: float, **kwargs) -> bool:
        """
        Custom exit that implements our virtual stop loss logic using the entry swing low
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        last_candle = dataframe.iloc[-1].squeeze()
        
        # Get the entry swing low at the time of trade entry
        trade_start_time = trade.open_date_utc
        entry_candle = dataframe[dataframe.index <= trade_start_time].iloc[-1]
        virtual_stop = entry_candle['entry_swing_low']  # This is our virtual stop loss level
        
        # Virtual stop loss conditions:
        # 1. Price crosses below EMA 25
        if current_rate < last_candle['ema_25']:
            return True
            
        # 2. Price hits the virtual stop loss (entry swing low)
        if current_rate < virtual_stop:
            return True
            
        # 3. Optional: Add maximum loss threshold (e.g., 2%)
        if current_profit < -0.02:
            return True
            
        return False