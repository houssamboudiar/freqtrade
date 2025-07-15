#!/usr/bin/env python3
"""
EMA Data to Redis Script
========================

This script fetches cryptocurrency price data, calculates EMA (Exponential Moving Average)
indicators, and stores the results in Redis for fast access by trading strategies.

Requirements:
- redis
- pandas
- numpy
- ccxt (for exchange data)
- python-dotenv (for environment variables)

Usage:
    python ema_to_redis.py
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import redis
import pandas as pd
import numpy as np
import ccxt
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EMARedisManager:
    """Manages EMA calculations and Redis storage"""
    
    def __init__(self, redis_host: str = 'localhost', redis_port: int = 6379, redis_db: int = 1):
        """
        Initialize the EMA Redis Manager
        
        Args:
            redis_host: Redis server host
            redis_port: Redis server port  
            redis_db: Redis database number (using db=1 to separate from freqtrade if needed)
        """
        try:
            self.redis_client = redis.Redis(
                host=redis_host, 
                port=redis_port, 
                db=redis_db,
                decode_responses=True
            )
            # Test connection
            self.redis_client.ping()
            logger.info(f"✅ Connected to Redis at {redis_host}:{redis_port}")
        except redis.ConnectionError as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            sys.exit(1)
            
        # Load environment variables
        load_dotenv()
        
        # Initialize exchange (using Binance like your freqtrade config)
        self.exchange = None
        self._init_exchange()
        
        # EMA periods to calculate
        self.ema_periods = [7, 25, 50, 63, 99, 200]
        
        # Timeframes to analyze
        self.timeframes = ['1w', '1d', '4h', '1h', '30m', '15m', '5m', '1m']
        
        # Trading pairs - can be easily extended
        self.pairs = [
            "BTC/USDT", "ETH/USDT", "BNB/USDT", "ADA/USDT", "XRP/USDT",
            "SOL/USDT", "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "MATIC/USDT",
            "LINK/USDT", "UNI/USDT", "LTC/USDT", "ATOM/USDT", "NEAR/USDT",
            "USUAL/USDT"  # Your current trading pair
        ]
        
    def _init_exchange(self):
        """Initialize the exchange connection"""
        try:
            api_key = os.getenv('BINANCE_API_KEY')
            api_secret = os.getenv('BINANCE_SECRET_KEY')
            
            self.exchange = ccxt.binance({
                'apiKey': api_key,
                'secret': api_secret,
                'sandbox': False,  # Set to True for testnet
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'spot'  # Use 'future' for futures
                }
            })
            
            # Test connection
            self.exchange.load_markets()
            logger.info("✅ Connected to Binance exchange")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize exchange: {e}")
            # Continue without exchange - can still work with sample data
            self.exchange = None
    
    def calculate_ema(self, prices: pd.Series, period: int) -> pd.Series:
        """
        Calculate Exponential Moving Average
        
        Args:
            prices: Price series (typically close prices)
            period: EMA period
            
        Returns:
            EMA values as pandas Series
        """
        return prices.ewm(span=period, adjust=False).mean()
    
    def fetch_ohlcv_data(self, symbol: str, timeframe: str, limit: int = 500) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV data from exchange for specific timeframe
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            timeframe: Timeframe ('1w', '1d', '4h', '1h', '30m', '15m', '5m', '1m')
            limit: Number of candles to fetch
            
        Returns:
            DataFrame with OHLCV data or None if failed
        """
        if not self.exchange:
            logger.warning(f"No exchange connection - using sample data for {symbol} {timeframe}")
            return self._generate_sample_data(symbol, timeframe, limit)
            
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            logger.info(f"✅ Fetched {len(df)} candles for {symbol} {timeframe}")
            return df
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch data for {symbol} {timeframe}: {e}")
            return self._generate_sample_data(symbol, timeframe, limit)
    
    def _generate_sample_data(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        """Generate sample OHLCV data for testing"""
        logger.info(f"Generating sample data for {symbol} {timeframe}")
        
        # Convert timeframe to minutes for timestamp calculation
        timeframe_minutes = {
            '1m': 1, '5m': 5, '15m': 15, '30m': 30, 
            '1h': 60, '4h': 240, '1d': 1440, '1w': 10080
        }
        
        interval_minutes = timeframe_minutes.get(timeframe, 5)
        
        # Generate timestamps
        now = datetime.now()
        timestamps = [now - timedelta(minutes=interval_minutes*i) for i in range(limit, 0, -1)]
        
        # Generate sample prices (random walk)
        base_price = 50000 if 'BTC' in symbol else 3000 if 'ETH' in symbol else 1.0
        prices = [base_price]
        
        # Adjust volatility based on timeframe (longer timeframes = more volatility)
        volatility_multiplier = {
            '1m': 0.0001, '5m': 0.0005, '15m': 0.001, '30m': 0.002,
            '1h': 0.005, '4h': 0.01, '1d': 0.02, '1w': 0.05
        }
        volatility = base_price * volatility_multiplier.get(timeframe, 0.001)
        
        for i in range(1, limit):
            change = np.random.normal(0, volatility)
            new_price = max(prices[-1] + change, base_price * 0.1)  # Prevent very low prices
            prices.append(new_price)
        
        # Create OHLCV data
        data = []
        for i, (ts, price) in enumerate(zip(timestamps, prices)):
            daily_volatility = volatility / base_price
            high = price * (1 + abs(np.random.normal(0, daily_volatility)))
            low = price * (1 - abs(np.random.normal(0, daily_volatility)))
            open_price = prices[i-1] if i > 0 else price
            volume = np.random.uniform(100, 10000)  # Higher volume range
            
            data.append({
                'timestamp': ts,
                'open': open_price,
                'high': high,
                'low': low,
                'close': price,
                'volume': volume
            })
        
        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)
        return df
    
    def calculate_emas_for_pair_timeframe(self, symbol: str, timeframe: str) -> Dict[str, Any]:
        """
        Calculate EMAs for a trading pair and specific timeframe
        
        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe ('1w', '1d', '4h', '1h', '30m', '15m', '5m', '1m')
            
        Returns:
            Dictionary containing EMA data and metadata for the timeframe
        """
        # Fetch OHLCV data for this timeframe
        df = self.fetch_ohlcv_data(symbol, timeframe)
        if df is None or df.empty:
            logger.error(f"No data available for {symbol} {timeframe}")
            return {}
        
        # Calculate EMAs
        ema_data = {
            'symbol': symbol,
            'timeframe': timeframe,
            'timestamp': datetime.now().isoformat(),
            'last_price': float(df['close'].iloc[-1]),
            'emas': {},
            'signals': {},
            'candle_data': {
                'open': float(df['open'].iloc[-1]),
                'high': float(df['high'].iloc[-1]),
                'low': float(df['low'].iloc[-1]),
                'close': float(df['close'].iloc[-1]),
                'volume': float(df['volume'].iloc[-1])
            }
        }
        
        # Calculate all EMA periods
        for period in self.ema_periods:
            if len(df) >= period:  # Only calculate if we have enough data
                ema_series = self.calculate_ema(df['close'], period)
                current_ema = float(ema_series.iloc[-1])
                prev_ema = float(ema_series.iloc[-2]) if len(ema_series) > 1 else current_ema
                
                # Calculate percentage distance from current price
                price_distance = ((ema_data['last_price'] - current_ema) / current_ema) * 100
                
                ema_data['emas'][f'ema_{period}'] = {
                    'value': current_ema,
                    'previous': prev_ema,
                    'trend': 'up' if current_ema > prev_ema else 'down',
                    'price_distance_pct': price_distance
                }
            else:
                logger.warning(f"Not enough data for EMA-{period} on {symbol} {timeframe}")
        
        # Calculate signals if we have the basic EMAs
        if 'ema_7' in ema_data['emas'] and 'ema_25' in ema_data['emas'] and 'ema_50' in ema_data['emas']:
            current_price = ema_data['last_price']
            ema_7 = ema_data['emas']['ema_7']['value']
            ema_25 = ema_data['emas']['ema_25']['value']
            ema_50 = ema_data['emas']['ema_50']['value']
            ema_200 = ema_data['emas'].get('ema_200', {}).get('value', 0)
            
            ema_data['signals'] = {
                'price_above_ema7': current_price > ema_7,
                'price_above_ema25': current_price > ema_25,
                'price_above_ema50': current_price > ema_50,
                'price_above_ema200': current_price > ema_200 if ema_200 else None,
                'ema7_above_ema25': ema_7 > ema_25,
                'ema25_above_ema50': ema_25 > ema_50,
                'ema50_above_ema200': ema_50 > ema_200 if ema_200 else None,
                'bullish_alignment': ema_7 > ema_25 > ema_50,
                'bearish_alignment': ema_7 < ema_25 < ema_50,
                'golden_cross_7_25': ema_7 > ema_25 and ema_data['emas']['ema_7']['trend'] == 'up',
                'death_cross_7_25': ema_7 < ema_25 and ema_data['emas']['ema_7']['trend'] == 'down'
            }
        
        return ema_data
    
    def save_to_redis(self, symbol: str, timeframe: str, data: Dict[str, Any], expiry_seconds: int = 7200):
        """
        Save EMA data to Redis with timeframe-specific keys
        
        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe
            data: EMA data dictionary
            expiry_seconds: Expiry time in seconds (default 2 hours)
        """
        if not data:
            return
            
        try:
            # Create Redis keys with timeframe
            base_key = f"ema_data:{symbol.replace('/', '_')}:{timeframe}"
            
            # Save main data
            self.redis_client.setex(
                base_key,
                expiry_seconds,
                json.dumps(data, indent=2)
            )
            
            # Save individual EMA values for quick access
            for ema_key, ema_info in data['emas'].items():
                redis_key = f"{base_key}:{ema_key}"
                self.redis_client.setex(redis_key, expiry_seconds, ema_info['value'])
            
            # Save signals
            if data['signals']:
                signals_key = f"{base_key}:signals"
                self.redis_client.setex(
                    signals_key,
                    expiry_seconds,
                    json.dumps(data['signals'])
                )
            
            # Save current price for quick access
            price_key = f"{base_key}:price"
            self.redis_client.setex(price_key, expiry_seconds, data['last_price'])
            
            # Update last update timestamp
            self.redis_client.setex(
                f"{base_key}:last_update",
                expiry_seconds,
                data['timestamp']
            )
            
            logger.info(f"✅ Saved EMA data for {symbol} {timeframe} to Redis")
            
        except Exception as e:
            logger.error(f"❌ Failed to save data to Redis for {symbol} {timeframe}: {e}")
    
    def get_from_redis(self, symbol: str, timeframe: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve EMA data from Redis for specific symbol and timeframe
        
        Args:
            symbol: Trading pair symbol
            timeframe: Timeframe
            
        Returns:
            EMA data dictionary or None if not found
        """
        try:
            key = f"ema_data:{symbol.replace('/', '_')}:{timeframe}"
            data = self.redis_client.get(key)
            
            if data:
                return json.loads(data)
            else:
                logger.warning(f"No data found in Redis for {symbol} {timeframe}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Failed to retrieve data from Redis for {symbol} {timeframe}: {e}")
            return None
    
    def update_all_pairs(self, selected_pairs: List[str] = None, selected_timeframes: List[str] = None):
        """
        Update EMA data for all configured pairs and timeframes
        
        Args:
            selected_pairs: List of specific pairs to update (if None, updates all)
            selected_timeframes: List of specific timeframes to update (if None, updates all)
        """
        pairs_to_process = selected_pairs if selected_pairs else self.pairs
        timeframes_to_process = selected_timeframes if selected_timeframes else self.timeframes
        
        total_combinations = len(pairs_to_process) * len(timeframes_to_process)
        logger.info(f"Starting EMA update for {len(pairs_to_process)} pairs × {len(timeframes_to_process)} timeframes = {total_combinations} combinations...")
        
        current_combination = 0
        
        for symbol in pairs_to_process:
            print(f"\n🪙 Processing {symbol}...")
            
            for timeframe in timeframes_to_process:
                current_combination += 1
                try:
                    logger.info(f"[{current_combination}/{total_combinations}] Processing {symbol} {timeframe}...")
                    ema_data = self.calculate_emas_for_pair_timeframe(symbol, timeframe)
                    
                    if ema_data:
                        self.save_to_redis(symbol, timeframe, ema_data)
                        self._print_summary(ema_data)
                    else:
                        logger.warning(f"No EMA data calculated for {symbol} {timeframe}")
                        
                except Exception as e:
                    logger.error(f"❌ Error processing {symbol} {timeframe}: {e}")
                    
                # Small delay to avoid overwhelming the exchange API
                time.sleep(0.1)
        
        logger.info("✅ EMA update completed for all pairs and timeframes")
    
    def _print_summary(self, data: Dict[str, Any]):
        """Print a summary of the EMA data"""
        symbol = data['symbol']
        timeframe = data['timeframe']
        price = data['last_price']
        
        print(f"   📊 {symbol} {timeframe} - Price: ${price:.4f}")
        
        # Show key EMAs with trends
        key_emas = ['ema_7', 'ema_25', 'ema_50', 'ema_200']
        ema_line = "      EMAs: "
        for ema_key in key_emas:
            if ema_key in data['emas']:
                ema_info = data['emas'][ema_key]
                trend_emoji = "📈" if ema_info['trend'] == 'up' else "📉"
                distance = ema_info['price_distance_pct']
                distance_str = f"({distance:+.1f}%)"
                period = ema_key.split('_')[1]
                ema_line += f"EMA{period}: {distance_str} {trend_emoji} | "
        
        print(ema_line.rstrip(" | "))
        
        # Show key signals
        if data['signals']:
            bullish_signals = sum(1 for signal, value in data['signals'].items() 
                                if value is True and 'above' in signal)
            total_signals = sum(1 for signal, value in data['signals'].items() 
                              if value is not None and 'above' in signal)
            
            alignment = "🟢 Bullish" if data['signals'].get('bullish_alignment') else \
                       "🔴 Bearish" if data['signals'].get('bearish_alignment') else "🟡 Mixed"
            
            print(f"      Signals: {bullish_signals}/{total_signals} bullish | {alignment}")
    
    def get_market_overview(self) -> Dict[str, Any]:
        """Get a market overview from Redis data"""
        overview = {
            'total_pairs': 0,
            'bullish_pairs': {},
            'bearish_pairs': {},
            'mixed_pairs': {},
            'last_update': datetime.now().isoformat()
        }
        
        try:
            # Get all EMA data keys
            all_keys = self.redis_client.keys("ema_data:*")
            main_keys = [key for key in all_keys if not any(x in key for x in [':ema_', ':signals', ':price', ':last_update'])]
            
            for timeframe in self.timeframes:
                overview['bullish_pairs'][timeframe] = []
                overview['bearish_pairs'][timeframe] = []
                overview['mixed_pairs'][timeframe] = []
            
            for key in main_keys:
                try:
                    data = json.loads(self.redis_client.get(key))
                    symbol = data['symbol']
                    timeframe = data['timeframe']
                    
                    if data['signals'].get('bullish_alignment'):
                        overview['bullish_pairs'][timeframe].append(symbol)
                    elif data['signals'].get('bearish_alignment'):
                        overview['bearish_pairs'][timeframe].append(symbol)
                    else:
                        overview['mixed_pairs'][timeframe].append(symbol)
                        
                except Exception as e:
                    logger.error(f"Error processing key {key}: {e}")
            
            overview['total_pairs'] = len(set(key.split(':')[1].replace('_', '/') for key in main_keys))
            
        except Exception as e:
            logger.error(f"Error generating market overview: {e}")
        
        return overview
    
    def print_market_overview(self):
        """Print a nice market overview"""
        overview = self.get_market_overview()
        
        print(f"\n📈 MARKET OVERVIEW - {overview['total_pairs']} pairs analyzed")
        print("=" * 60)
        
        for timeframe in self.timeframes:
            bullish_count = len(overview['bullish_pairs'].get(timeframe, []))
            bearish_count = len(overview['bearish_pairs'].get(timeframe, []))
            mixed_count = len(overview['mixed_pairs'].get(timeframe, []))
            total = bullish_count + bearish_count + mixed_count
            
            if total > 0:
                print(f"{timeframe:>4}: 🟢{bullish_count:>2} 🔴{bearish_count:>2} 🟡{mixed_count:>2} | "
                      f"Bullish: {(bullish_count/total)*100:.0f}%")
        
        print("=" * 60)
    
    def list_redis_keys(self):
        """List all EMA-related keys in Redis"""
        try:
            keys = self.redis_client.keys("ema_data:*")
            if keys:
                print(f"\n📝 Found {len(keys)} EMA keys in Redis:")
                for key in sorted(keys):
                    ttl = self.redis_client.ttl(key)
                    print(f"   {key} (TTL: {ttl}s)")
            else:
                print("📝 No EMA keys found in Redis")
        except Exception as e:
            logger.error(f"❌ Error listing Redis keys: {e}")
    
    def configure_pairs(self, pairs_list: List[str]):
        """
        Configure which pairs to analyze
        
        Args:
            pairs_list: List of trading pairs (e.g., ["BTC/USDT", "ETH/USDT"])
        """
        self.pairs = pairs_list
        logger.info(f"Configured {len(self.pairs)} pairs for analysis: {', '.join(self.pairs)}")
    
    def configure_timeframes(self, timeframes_list: List[str]):
        """
        Configure which timeframes to analyze
        
        Args:
            timeframes_list: List of timeframes (e.g., ["1h", "4h", "1d"])
        """
        self.timeframes = timeframes_list
        logger.info(f"Configured {len(self.timeframes)} timeframes for analysis: {', '.join(self.timeframes)}")
    
    def configure_ema_periods(self, periods_list: List[int]):
        """
        Configure which EMA periods to calculate
        
        Args:
            periods_list: List of EMA periods (e.g., [7, 25, 50, 200])
        """
        self.ema_periods = periods_list
        logger.info(f"Configured {len(self.ema_periods)} EMA periods: {self.ema_periods}")
        

def main():
    """Main function with options for selective updates"""
    print("🚀 Multi-Timeframe EMA to Redis Script")
    print("=" * 60)
    
    # Initialize the manager
    manager = EMARedisManager()
    
    # Show current Redis keys
    manager.list_redis_keys()
    
    # For testing, you can update specific pairs/timeframes:
    # manager.update_all_pairs(
    #     selected_pairs=["BTC/USDT", "ETH/USDT"], 
    #     selected_timeframes=["1h", "4h", "1d"]
    # )
    
    # Update all pairs and timeframes
    print(f"\n🔄 Updating {len(manager.pairs)} pairs across {len(manager.timeframes)} timeframes...")
    print(f"EMA Periods: {manager.ema_periods}")
    print(f"Timeframes: {manager.timeframes}")
    print()
    
    manager.update_all_pairs()
    
    # Show market overview
    manager.print_market_overview()
    
    # Show Redis keys after update
    print("\n" + "=" * 60)
    manager.list_redis_keys()
    
    print(f"\n✨ Script completed successfully!")
    print(f"\nRedis Data Structure:")
    print(f"ema_data:{{SYMBOL}}:{{TIMEFRAME}} - Complete EMA data")
    print(f"ema_data:{{SYMBOL}}:{{TIMEFRAME}}:ema_{{PERIOD}} - Individual EMA values")
    print(f"ema_data:{{SYMBOL}}:{{TIMEFRAME}}:signals - Trading signals")
    print(f"ema_data:{{SYMBOL}}:{{TIMEFRAME}}:price - Current price")
    print(f"\nExample Redis commands:")
    print(f"docker exec -it freqtrade_redis redis-cli")
    print(f"redis> SELECT 1")
    print(f"redis> KEYS ema_data:BTC_USDT:*")
    print(f"redis> GET ema_data:BTC_USDT:1d")
    print(f"redis> GET ema_data:BTC_USDT:1h:ema_25")


if __name__ == "__main__":
    main()
