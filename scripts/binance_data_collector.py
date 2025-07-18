import datetime
from binance.client import Client
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator
import time
from typing import List, Dict, Tuple
import redis
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Thread-local storage for client instances
thread_local = threading.local()

# Initialize Redis connection with retry logic
def connect_to_redis(max_retries=5, retry_delay=2):
    for attempt in range(max_retries):
        try:
            client = redis.Redis(
                host='localhost',
                port=6379,
                decode_responses=True,
                socket_timeout=5
            )
            # Test the connection
            client.ping()
            print("Successfully connected to Redis!")
            return client
        except redis.ConnectionError as e:
            if attempt < max_retries - 1:
                print(f"Failed to connect to Redis (attempt {attempt + 1}/{max_retries}). Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                raise Exception("Could not connect to Redis after several attempts. Make sure Redis is running in Docker.") from e

redis_client = connect_to_redis()

def get_thread_binance_client():
    """Get thread-local Binance client instance."""
    if not hasattr(thread_local, 'binance_client'):
        # Initialize client with optimized timeout and connection pooling
        thread_local.binance_client = Client(
            None,  # API key
            None,  # API secret
            {"timeout": 15, "verify": True}  # Reduced timeout, keep SSL verification
        )
    return thread_local.binance_client

def get_all_symbols() -> List[str]:
    """Return only the 5 specified symbols for data collection."""
    return ['XRPUSDT', 'LTCUSDT', 'SUSHIUSDT', 'EPICUSDT', 'LOKAUSDT']

def fetch_historical_data(symbol: str, interval: str) -> pd.DataFrame:
    """Fetch 6 months of historical data for a symbol.
    
    Args:
        symbol: The trading pair symbol
        interval: The candle interval ('1m', '1h', or '1d')
    """
    client = get_thread_binance_client()  # Get thread-local client instance
    
    end_time = int(datetime.datetime.now().timestamp() * 1000)
    
    # Set 6 months (180 days) for all intervals
    six_months_ms = 180 * 24 * 60 * 60 * 1000  # 6 months in milliseconds
    start_time = end_time - six_months_ms
    
    # Fetch historical klines/candlestick data for 6 months
    klines = client.get_historical_klines(
        symbol,
        interval,
        str(start_time),
        str(end_time)
    )
    
    # Create DataFrame
    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_asset_volume', 'number_of_trades',
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
    ])
    
    # Convert timestamp to datetime
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    
    # Convert all numeric columns to float
    numeric_columns = [
        'open', 'high', 'low', 'close', 'volume',
        'quote_asset_volume', 'number_of_trades',
        'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume'
    ]
    for col in numeric_columns:
        df[col] = df[col].astype(float)
    
    return df

def calculate_emas(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate EMAs for different periods."""
    periods = [7, 15, 25, 55, 99, 200, 300]  # Updated EMA periods
    
    for period in periods:
        ema = EMAIndicator(close=df['close'], window=period)
        df[f'ema_{period}'] = ema.ema_indicator()
    
    return df

def calculate_volume_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate additional volume metrics."""
    # Calculate total volume (already exists as 'volume')
    df['total_volume'] = df['volume']
    
    # Calculate selling and buying volume using taker buy volume
    df['buying_volume'] = df['taker_buy_base_asset_volume']
    df['selling_volume'] = df['volume'] - df['taker_buy_base_asset_volume']
    
    return df

def store_data(symbol: str, df: pd.DataFrame, interval: str):
    """Store the processed data in Redis using optimized pipeline for better performance.
    
    Args:
        symbol: The trading pair symbol
        df: DataFrame containing the candle data
        interval: The candle interval ('1m', '1h', or '1d')
    """
    # Use a single pipeline transaction for maximum speed
    with redis_client.pipeline(transaction=False) as pipe:  # Non-transactional pipeline for speed
        # Store full historical data with interval-specific keys
        history_key = f"crypto:{symbol}:{interval}:history"
        
        # Clear old data first
        pipe.delete(history_key)
        
        # Prepare all records in batch - convert timestamp once
        data_records = []
        for _, record in df.iterrows():
            record_dict = record.to_dict()
            record_dict['timestamp'] = record_dict['timestamp'].isoformat()
            data_records.append(json.dumps(record_dict))
        
        # Batch insert all records at once
        if data_records:
            pipe.rpush(history_key, *data_records)
        
        # Store latest data
        latest_key = f"crypto:{symbol}:{interval}:latest"
        latest_data = df.iloc[-1].to_dict()
        latest_data['timestamp'] = latest_data['timestamp'].isoformat()
        pipe.hset(latest_key, mapping=latest_data)
        
        # Set expirations based on 6-month data retention
        if interval == Client.KLINE_INTERVAL_1MINUTE:
            pipe.expire(history_key, 7 * 24 * 60 * 60)      # 7 days for 1m history (6 months is too much for 1m)
            pipe.expire(latest_key, 60 * 60)                # 1 hour for 1m latest
        elif interval == Client.KLINE_INTERVAL_1HOUR:
            pipe.expire(history_key, 180 * 24 * 60 * 60)    # 6 months for 1h history
            pipe.expire(latest_key, 24 * 60 * 60)           # 24 hours for 1h latest
        else:  # Daily interval
            pipe.expire(history_key, 180 * 24 * 60 * 60)    # 6 months for daily history
            pipe.expire(latest_key, 7 * 24 * 60 * 60)       # 7 days for daily latest
        
        # Execute all commands in a single batch
        pipe.execute()
        
    # Reduced logging for speed - only log completion
    print(f"✅ {symbol} {interval}: {len(df)} candles")

def process_symbol_interval(symbol: str, interval: str) -> Tuple[bool, str, int]:
    """Process a single symbol and interval combination with optimized performance."""
    try:
        # Fetch historical data
        df = fetch_historical_data(symbol, interval)
        
        # Calculate EMAs and volume metrics in parallel-friendly way
        df = calculate_emas(df)
        df = calculate_volume_metrics(df)
        
        # Store data in Redis with optimized pipeline
        store_data(symbol, df, interval)
        
        candle_count = len(df)
        return True, f"{symbol} {interval} ✅ ({candle_count} candles)", candle_count
        
    except Exception as e:
        return False, f"{symbol} {interval} ❌: {str(e)}", 0

def parallel_process_symbols(symbols: List[str], max_workers: int = 20):
    """Process multiple symbols in parallel with optimized performance."""
    intervals = [Client.KLINE_INTERVAL_1MINUTE, Client.KLINE_INTERVAL_1HOUR, Client.KLINE_INTERVAL_1DAY]
    total_tasks = len(symbols) * len(intervals)
    completed_tasks = 0
    success_count = 0
    
    print(f"\n🚀 Fast processing {len(symbols)} symbols with {len(intervals)} intervals each...")
    print(f"⚡ Using {max_workers} worker threads for maximum speed")
    
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks at once for better CPU utilization
        future_to_task = {
            executor.submit(process_symbol_interval, symbol, interval): (symbol, interval)
            for symbol in symbols
            for interval in intervals
        }
        
        # Process completed tasks as they finish
        for future in as_completed(future_to_task):
            symbol, interval = future_to_task[future]
            completed_tasks += 1
            
            try:
                success, message, candle_count = future.result()
                if success:
                    success_count += 1
                    progress = (completed_tasks / total_tasks) * 100
                    print(f"[{completed_tasks}/{total_tasks}] {progress:.1f}% - {message}")
                else:
                    print(f"[{completed_tasks}/{total_tasks}] ❌ {message}")
                
            except Exception as e:
                print(f"[{completed_tasks}/{total_tasks}] ❌ Error: {symbol} {interval}: {str(e)}")
    
    elapsed_time = time.time() - start_time
    tasks_per_second = total_tasks / elapsed_time if elapsed_time > 0 else 0
    
    print(f"\n⏱️  Completed in {elapsed_time:.2f} seconds ({tasks_per_second:.1f} tasks/sec)")
    return success_count, total_tasks

def process_symbol_batch(symbols_batch: List[str], max_workers: int) -> Tuple[int, int]:
    """Process a batch of symbols."""
    return parallel_process_symbols(symbols_batch, max_workers)

def main():
    """Main function to collect 6 months of BTCUSDT data for fast testing."""
    print("=== ⚡ 6-Month Data Collection for 5 Coins ===")
    print("Collecting for: XRPUSDT, LTCUSDT, SUSHIUSDT, EPICUSDT, LOKAUSDT")

    symbols = get_all_symbols()
    print(f"Found {len(symbols)} symbols: {', '.join(symbols)}")
    print("📅 Collecting 6 months of historical data for all symbols...")

    max_workers = 10  # Use more workers for multiple symbols

    print(f"\n🚀 Processing {len(symbols)} symbols with {max_workers} threads...")
    print("⏱️  Expected data volumes per symbol:")
    print("   • 1m intervals: ~259,200 candles (6 months)")
    print("   • 1h intervals: ~4,320 candles (6 months)")
    print("   • 1d intervals: ~180 candles (6 months)")

    success_count, total_tasks = parallel_process_symbols(symbols, max_workers)

    print(f"\n🎉 6-month data collection completed for all symbols!")
    print(f"✅ Successfully processed {success_count} out of {total_tasks} tasks")
    success_rate = (success_count / total_tasks) * 100 if total_tasks > 0 else 0
    print(f"📊 Success rate: {success_rate:.1f}%")

if __name__ == "__main__":
    main()
