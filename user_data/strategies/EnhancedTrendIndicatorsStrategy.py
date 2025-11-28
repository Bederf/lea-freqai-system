from pandas import DataFrame
from functools import reduce
import talib.abstract as ta
from freqtrade.strategy import IStrategy
import qtpylib.indicators as qtpylib



class EnhancedTrendIndicatorsStrategy(IStrategy):
    INTERFACE_VERSION = 3

    # Define minimal ROI and stoploss
    minimal_roi = {
        "0": 0.10,
        "10": 0.05,
        "30": 0.01,
        "60": 0
    }

    stoploss = -0.10  # 10% stoploss

    timeframe = '1h'  # Adjust as necessary

    # Optimal pairs to trade
    startup_candle_count = 200  # Number of candles to initialize indicators

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Calculate EMA indicators
        dataframe['ema50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema200'] = ta.EMA(dataframe, timeperiod=200)
        
        # Calculate RSI indicator
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # Calculate MACD and Signal Line
        macd, macdsignal, macdhist = ta.MACD(dataframe['close'], fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe['macd'] = macd
        dataframe['macdsignal'] = macdsignal
        
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        conditions = []
        
        # Check for an uptrend condition
        conditions.append(dataframe['close'] > dataframe['ema50'])
        conditions.append(dataframe['ema50'] > dataframe['ema200'])
        conditions.append(dataframe['rsi'] < 70)
        conditions.append(dataframe['macd'] > dataframe['macdsignal'])

        # Combine conditions using bitwise AND (Fixed: all() was evaluating boolean)
        entry_condition = qtpylib.crossed_above(dataframe['close'], dataframe['ema50']) & reduce(lambda x, y: x & y, conditions)

        # Set enter_long signal
        dataframe.loc[entry_condition, 'enter_long'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Define exit conditions
        dataframe.loc[
            (dataframe['rsi'] > 70) | 
            (dataframe['macd'] < dataframe['macdsignal']), 
            'exit_long'] = 1

        return dataframe
