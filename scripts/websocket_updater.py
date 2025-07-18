
import sys
import gc
import signal
import traceback
import asyncio
import threading
import time
import json
import numpy as np
import pandas as pd
import websockets
import redis.asyncio as aioredis
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Set
from pathlib import Path
from ta.trend import EMAIndicator
from concurrent.futures import ThreadPoolExecutor
import os
from colorama import Fore, Back, Style, init

# Helper functions for technical indicators
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

# Initialize colorama for cross-platform colored output
try:
    from colorama import Fore, Back, Style, init
    init(autoreset=True)
    COLORAMA_AVAILABLE = True
except ImportError:
    print("Note: colorama not installed. Install with 'pip install colorama' for colored output.")
    # Define dummy color constants
    class DummyColor:
        def __getattr__(self, name):
            return ""
        # Common color attributes
        RED = ""
        GREEN = ""
        YELLOW = ""
        BLUE = ""
        CYAN = ""
        WHITE = ""
        LIGHTBLACK_EX = ""
        RESET_ALL = ""
    
    Fore = Back = Style = DummyColor()
    COLORAMA_AVAILABLE = False

async def connect_to_redis():
    """Connect to Redis using async client."""
    try:
        redis_client = aioredis.Redis(
            host='localhost',
            port=6379,
            db=0,
            decode_responses=True
        )
        await redis_client.ping()
        print("Successfully connected to Redis!")
        return redis_client
    except Exception as e:
        print(f"Error connecting to Redis: {str(e)}")
        print(f"Error details:\n{traceback.format_exc()}")
        return None

# Thread-local storage for REST client (removed - no longer needed for historical data)
thread_local = threading.local()

class BinanceWebSocketManager:
    async def fill_gaps_on_startup(self):
        """Robustly check for and fill all missing candles in Redis before starting live collection."""
        from binance.client import Client
        client = Client(None, None, {"timeout": 15, "verify": True})
        timeframes = ['1m', '1h', '1d']
        interval_map = {'1m': '1m', '1h': '1h', '1d': '1d'}
        now = datetime.now(timezone.utc)
        for symbol in self.symbols:
            for interval in timeframes:
                history_key = f"crypto:{symbol}:{interval}:history"
                # Loop until no more gaps are found
                while True:
                    data = await self.redis.lrange(history_key, 0, -1)
                    # Determine expected interval
                    if interval == '1m':
                        expected_delta = timedelta(minutes=1)
                    elif interval == '1h':
                        expected_delta = timedelta(hours=1)
                    else:
                        expected_delta = timedelta(days=1)
                    # If no data or only one candle, fetch all available history
                    if not data or len(data) < 2:
                        print(f"[GAP FILL] {symbol} {interval}: No or only one candle in Redis, fetching full history...")
                        start_dt = datetime(2017, 8, 17, tzinfo=timezone.utc)
                        start_ms = int(start_dt.timestamp() * 1000)
                        end_ms = int(now.timestamp() * 1000)
                        klines = client.get_historical_klines(
                            symbol=symbol,
                            interval=interval_map[interval],
                            start_str=str(start_ms),
                            end_str=str(end_ms)
                        )
                        new_candles = []
                        for k in klines:
                            candle = {
                                'timestamp': pd.to_datetime(k[0], unit='ms').isoformat(),
                                'open': float(k[1]),
                                'high': float(k[2]),
                                'low': float(k[3]),
                                'close': float(k[4]),
                                'volume': float(k[5]),
                                'close_time': k[6],
                                'quote_asset_volume': float(k[7]),
                                'number_of_trades': int(k[8]),
                                'taker_buy_base_asset_volume': float(k[9]),
                                'taker_buy_quote_asset_volume': float(k[10])
                            }
                            new_candles.append(candle)
                        if new_candles:
                            df = pd.DataFrame(new_candles)
                            df['timestamp'] = pd.to_datetime(df['timestamp'])
                            df = calculate_emas(df)
                            df = calculate_volume_metrics(df)
                            all_candles = [row.to_dict() for _, row in df.iterrows()]
                            for c in all_candles:
                                if isinstance(c['timestamp'], pd.Timestamp):
                                    c['timestamp'] = c['timestamp'].isoformat()
                            all_candles.sort(key=lambda x: pd.to_datetime(x['timestamp']))
                            await self.redis.delete(history_key)
                            candle_jsons = [json.dumps(c) for c in all_candles]
                            if candle_jsons:
                                await self.redis.rpush(history_key, *candle_jsons)
                                await self.redis.expire(history_key, 365 * 24 * 60 * 60)
                            print(f"[GAP FILL] {symbol} {interval}: Inserted {len(new_candles)} candles.")
                        else:
                            print(f"[GAP FILL] {symbol} {interval}: No candles found from Binance.")
                        break  # No need to check for more gaps
                    # Parse and sort all candles
                    candles = [json.loads(item) for item in data]
                    for c in candles:
                        c['timestamp'] = pd.to_datetime(c['timestamp'])
                    candles.sort(key=lambda x: x['timestamp'])
                    # Scan for gaps between all consecutive candles
                    gaps = []
                    for i in range(1, len(candles)):
                        prev_time = candles[i-1]['timestamp']
                        curr_time = candles[i]['timestamp']
                        expected_time = prev_time + expected_delta
                        if curr_time > expected_time:
                            # There may be multiple missing candles, fill the whole gap
                            gaps.append((expected_time, curr_time))
                    # Also check for a gap at the end (last candle to now)
                    last_time = candles[-1]['timestamp']
                    next_time = last_time + expected_delta
                    if next_time < now:
                        gaps.append((next_time, now))
                    if not gaps:
                        break  # No more gaps, done
                    # Fill all gaps found in this pass
                    for gap_start, gap_end in gaps:
                        print(f"[GAP FILL] {symbol} {interval}: Filling from {gap_start} to {gap_end}")
                        start_ms = int(gap_start.timestamp() * 1000)
                        end_ms = int(gap_end.timestamp() * 1000)
                        klines = client.get_historical_klines(
                            symbol=symbol,
                            interval=interval_map[interval],
                            start_str=str(start_ms),
                            end_str=str(end_ms)
                        )
                        new_candles = []
                        for k in klines:
                            candle = {
                                'timestamp': pd.to_datetime(k[0], unit='ms').isoformat(),
                                'open': float(k[1]),
                                'high': float(k[2]),
                                'low': float(k[3]),
                                'close': float(k[4]),
                                'volume': float(k[5]),
                                'close_time': k[6],
                                'quote_asset_volume': float(k[7]),
                                'number_of_trades': int(k[8]),
                                'taker_buy_base_asset_volume': float(k[9]),
                                'taker_buy_quote_asset_volume': float(k[10])
                            }
                            new_candles.append(candle)
                        if new_candles:
                            # Calculate indicators
                            df = pd.DataFrame(new_candles)
                            df['timestamp'] = pd.to_datetime(df['timestamp'])
                            df = calculate_emas(df)
                            df = calculate_volume_metrics(df)
                            # Merge with existing candles, deduplicate, and sort
                            all_candles = candles + [row.to_dict() for _, row in df.iterrows()]
                            for c in all_candles:
                                if isinstance(c['timestamp'], pd.Timestamp):
                                    c['timestamp'] = c['timestamp'].isoformat()
                            # Remove duplicates by timestamp
                            seen = set()
                            deduped = []
                            for c in all_candles:
                                ts = c['timestamp']
                                if ts not in seen:
                                    seen.add(ts)
                                    deduped.append(c)
                            deduped.sort(key=lambda x: pd.to_datetime(x['timestamp']))
                            # Clear and rebuild the Redis list
                            await self.redis.delete(history_key)
                            candle_jsons = [json.dumps(c) for c in deduped]
                            if candle_jsons:
                                await self.redis.rpush(history_key, *candle_jsons)
                                await self.redis.expire(history_key, 365 * 24 * 60 * 60)
                            print(f"[GAP FILL] {symbol} {interval}: Inserted {len(new_candles)} candles.")
                        else:
                            print(f"[GAP FILL] {symbol} {interval}: No missing candles found from Binance.")
                    # After filling, loop again to check for new gaps
    def __init__(self):
        # Existing initialization
        self.symbols: Set[str] = set()
        self.candle_data: Dict[str, Dict[str, List]] = {}
        self.last_kline_update: Dict[str, datetime] = {}
        self.websockets: Dict[str, websockets.WebSocketClientProtocol] = {}
        self.running = False
        self.STREAMS_PER_CONNECTION = 200
        self.redis = None  # Will be set in connect()

        # New monitoring statistics
        self.stats = {
            'messages_received': 0,
            'messages_processed': 0,
            'errors': 0,
            'reconnections': 0,
            'start_time': time.time(),
            'last_error': None,
            'updates_by_interval': {'1m': 0, '1h': 0, '1d': 0},
            'data_gaps': {},  # Track time gaps in data
            'redis_errors': 0,
            'processing_times': [],  # Track processing times
            'redis_latency': [],    # Track Redis operation latency
            'last_update_time': None,
            'next_refresh_time': None,
        }
        
        # Data integrity tracking
        self.sequence_numbers: Dict[str, Dict[str, int]] = {}  # Track message sequence for each symbol/interval
        self.last_candle_times: Dict[str, Dict[str, int]] = {}  # Track last candle timestamp for gaps
        
        # Display settings
        self.last_display_update = 0
        self.display_interval = 2.0  # Update display every 2 seconds
        
    def get_active_connections_count(self) -> tuple:
        """Get count of active WebSocket connections."""
        try:
            active = 0
            total = len(self.websockets)
            
            for ws in self.websockets.values():
                if ws:
                    try:
                        # Check if websocket is still open by checking its state
                        if hasattr(ws, 'state') and ws.state.name in ['OPEN', 'CONNECTING']:
                            active += 1
                        elif hasattr(ws, 'open') and ws.open:
                            active += 1
                        else:
                            # Try a simple check - if we can access the websocket without error, consider it active
                            active += 1
                    except:
                        # If any error occurs, consider this connection inactive
                        pass
            
            return active, total
        except Exception as e:
            print(f"Error checking connection status: {e}")
            return 0, len(self.websockets)
    
    def clear_screen(self):
        """Clear the terminal screen."""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def get_redis_status(self) -> tuple:
        """Get Redis connection status and info."""
        if not self.redis:
            return "DISCONNECTED", Fore.RED + "❌ Not Connected" + Style.RESET_ALL
        
        try:
            # This is a quick way to check if Redis is responsive
            # We'll check this in the monitoring loop
            return "CONNECTED", Fore.GREEN + "✅ Connected" + Style.RESET_ALL
        except:
            return "ERROR", Fore.YELLOW + "⚠️ Connection Issues" + Style.RESET_ALL
    
    def format_uptime(self, seconds: float) -> str:
        """Format uptime in a readable format."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def format_time_until_refresh(self) -> str:
        """Calculate and format time until next refresh."""
        if not self.stats['next_refresh_time']:
            return "N/A"
        
        now = datetime.now()
        time_diff = self.stats['next_refresh_time'] - now
        
        if time_diff.total_seconds() <= 0:
            return "Now"
        
        minutes = int(time_diff.total_seconds() // 60)
        seconds = int(time_diff.total_seconds() % 60)
        return f"{minutes:02d}:{seconds:02d}"
    
    def print_enhanced_status(self):
        """Print an enhanced status display with all requested information."""
        current_time = time.time()
        
        # Only update display at specified intervals
        if current_time - self.last_display_update < self.display_interval:
            return
        
        # Safety check to prevent infinite loops
        if not self.running:
            return
        
        self.last_display_update = current_time
        
        # Clear screen for fresh display
        self.clear_screen()
        
        # Header
        print(f"{Fore.CYAN}{'='*80}")
        print(f"{Fore.CYAN}🔄 BINANCE WEBSOCKET DATA COLLECTOR - LIVE STATUS")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
        print()
        
        # Redis Connection Status
        redis_status, redis_display = self.get_redis_status()
        print(f"{Fore.WHITE}📡 REDIS CONNECTION:{Style.RESET_ALL}")
        print(f"   Status: {redis_display}")
        if self.stats['redis_latency']:
            avg_latency = np.mean(self.stats['redis_latency'][-100:]) * 1000
            latency_color = Fore.GREEN if avg_latency < 10 else Fore.YELLOW if avg_latency < 50 else Fore.RED
            print(f"   Latency: {latency_color}{avg_latency:.1f}ms{Style.RESET_ALL}")
        print()
        
        # WebSocket Connections
        active_connections, total_connections = self.get_active_connections_count()
        connection_color = Fore.GREEN if active_connections == total_connections else Fore.YELLOW if active_connections > 0 else Fore.RED
        
        print(f"{Fore.WHITE}🔌 WEBSOCKET CONNECTIONS:{Style.RESET_ALL}")
        print(f"   Active: {connection_color}{active_connections}/{total_connections}{Style.RESET_ALL}")
        print(f"   Reconnections: {Fore.YELLOW}{self.stats['reconnections']}{Style.RESET_ALL}")
        print()
        
        # Coins Monitored
        print(f"{Fore.WHITE}💰 COINS MONITORED:{Style.RESET_ALL}")
        print(f"   Total Pairs: {Fore.GREEN}{len(self.symbols)}{Style.RESET_ALL}")
        
        # Show most active pairs
        if self.last_kline_update:
            recent_updates = {}
            now = datetime.now()
            for key, last_update in self.last_kline_update.items():
                symbol = key.split(':')[0]
                if symbol not in recent_updates:
                    recent_updates[symbol] = 0
                if (now - last_update).total_seconds() < 300:  # Updates in last 5 minutes
                    recent_updates[symbol] += 1
            
            active_pairs = len([s for s in recent_updates.values() if s > 0])
            print(f"   Active (5min): {Fore.GREEN}{active_pairs}{Style.RESET_ALL}")
        print()
        
        # Timing Information
        uptime = current_time - self.stats['start_time']
        print(f"{Fore.WHITE}⏰ TIMING INFORMATION:{Style.RESET_ALL}")
        print(f"   Uptime: {Fore.CYAN}{self.format_uptime(uptime)}{Style.RESET_ALL}")
        
        # Last update timing
        if self.stats['last_update_time']:
            last_update_ago = current_time - self.stats['last_update_time']
            update_color = Fore.GREEN if last_update_ago < 10 else Fore.YELLOW if last_update_ago < 60 else Fore.RED
            print(f"   Last Update: {update_color}{last_update_ago:.1f}s ago{Style.RESET_ALL}")
        else:
            print(f"   Last Update: {Fore.LIGHTBLACK_EX}N/A{Style.RESET_ALL}")
        
        # Processing time
        if self.stats['processing_times']:
            avg_processing = np.mean(self.stats['processing_times'][-100:]) * 1000
            processing_color = Fore.GREEN if avg_processing < 10 else Fore.YELLOW if avg_processing < 50 else Fore.RED
            print(f"   Avg Processing: {processing_color}{avg_processing:.1f}ms{Style.RESET_ALL}")
        
        # Next refresh
        next_refresh = self.format_time_until_refresh()
        print(f"   Next Refresh: {Fore.BLUE}{next_refresh}{Style.RESET_ALL}")
        print()
        
        # Statistics
        print(f"{Fore.WHITE}📈 STATISTICS:{Style.RESET_ALL}")
        success_rate = (self.stats['messages_processed'] / max(1, self.stats['messages_received'])) * 100
        success_color = Fore.GREEN if success_rate > 95 else Fore.YELLOW if success_rate > 90 else Fore.RED
        
        print(f"   Messages: {Fore.CYAN}{self.stats['messages_received']:,}{Style.RESET_ALL} received | "
              f"{Fore.CYAN}{self.stats['messages_processed']:,}{Style.RESET_ALL} processed")
        print(f"   Success Rate: {success_color}{success_rate:.1f}%{Style.RESET_ALL}")
        print(f"   Errors: {Fore.RED}{self.stats['errors']}{Style.RESET_ALL} | "
              f"Redis Errors: {Fore.RED}{self.stats['redis_errors']}{Style.RESET_ALL}")
        
        # Updates by interval
        print(f"   Updates: ", end="")
        for interval, count in self.stats['updates_by_interval'].items():
            print(f"{interval}={Fore.GREEN}{count:,}{Style.RESET_ALL} ", end="")
        print()
        
        # Data gaps
        if self.stats['data_gaps']:
            total_gaps = sum(len(gaps) for gaps in self.stats['data_gaps'].values())
            print(f"   Data Gaps: {Fore.YELLOW}{total_gaps}{Style.RESET_ALL} detected")
        print()
        
        # Footer
        print(f"{Fore.LIGHTBLACK_EX}{'─' * 80}")
        print(f"{Fore.LIGHTBLACK_EX}Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
              f"Refresh rate: {self.display_interval}s{Style.RESET_ALL}")
        print(f"{Fore.LIGHTBLACK_EX}{'─' * 80}{Style.RESET_ALL}")
        
    async def create_connection(self, streams: List[str], connection_id: str):
        """Create a single WebSocket connection for a group of streams."""
        stream_url = f"wss://stream.binance.com:9443/stream?streams={'/'.join(streams)}"
        retry_count = 0
        max_retries = 5
        base_delay = 5  # Base delay in seconds
        
        while self.running:
            try:
                async with websockets.connect(stream_url) as ws:
                    self.websockets[connection_id] = ws
                    # Silently establish connection (status shown in display)
                    retry_count = 0  # Reset retry count on successful connection
                    await self.handle_messages(ws, connection_id)
                    
            except websockets.ConnectionClosed as e:
                print(f"WebSocket connection {connection_id} closed: {str(e)}")
            except Exception as e:
                print(f"WebSocket connection error ({connection_id}): {str(e)}")
            
            if not self.running:
                break
                
            # Implement exponential backoff for reconnection
            retry_count += 1
            if retry_count > max_retries:
                print(f"Maximum retry attempts ({max_retries}) reached for connection {connection_id}")
                print("Will continue retrying with maximum delay")
                retry_count = max_retries
            
            delay = min(base_delay * (2 ** (retry_count - 1)), 60)  # Cap at 60 seconds
            print(f"Reconnecting {connection_id} in {delay} seconds... (Attempt {retry_count})")
            await asyncio.sleep(delay)

    async def connect(self):
        """Connect to Redis and Binance WebSocket streams."""
        # Connect to Redis first
        self.redis = await connect_to_redis()
        if not self.redis:
            print("Failed to connect to Redis. Exiting...")
            return

        # Monitor the specified 5 coins
        self.symbols = {'XRPUSDT', 'LTCUSDT', 'SUSHIUSDT', 'EPICUSDT', 'LOKAUSDT'}
        print("Monitoring: XRPUSDT, LTCUSDT, SUSHIUSDT, EPICUSDT, LOKAUSDT")

        # Initialize data structures for each symbol
        for symbol in self.symbols:
            self.candle_data[symbol] = {
                '1m': [], '1h': [], '1d': []
            }

        # Create stream lists for each symbol
        all_streams = []
        for symbol in self.symbols:
            symbol_lower = symbol.lower()
            all_streams.extend([
                f"{symbol_lower}@kline_1m",
                f"{symbol_lower}@kline_1h",
                f"{symbol_lower}@kline_1d"
            ])

        # Split streams into chunks to avoid URL length limit
        stream_chunks = [
            all_streams[i:i + self.STREAMS_PER_CONNECTION]
            for i in range(0, len(all_streams), self.STREAMS_PER_CONNECTION)
        ]

        # Silently create WebSocket connections (status shown in display)
        self.running = True

        # Create tasks for each connection
        tasks = []
        for i, streams in enumerate(stream_chunks):
            connection_id = f"conn_{i+1}"
            task = asyncio.create_task(self.create_connection(streams, connection_id))
            tasks.append(task)

        # Wait for all connections
        await asyncio.gather(*tasks)

    async def handle_messages(self, websocket, connection_id):
        """Handle incoming WebSocket messages."""
        update_counts = {symbol: {interval: 0 for interval in ['1m', '1h', '1d']} for symbol in self.symbols}
        
        while self.running:
            try:
                message = await websocket.recv()
                self.stats['messages_received'] += 1
                
                data = json.loads(message)
                
                # Extract kline data
                kline = data['data']['k']
                symbol = kline['s']
                interval = kline['i']  # '1m', '1h', '1d'
                
                # Convert interval to our format
                interval_map = {'1m': '1m', '1h': '1h', '1d': '1d'}
                our_interval = interval_map[interval]
                
                # Process the candle data
                await self.process_kline(symbol, our_interval, kline)
                
                # Update counts for status
                update_counts[symbol][our_interval] = update_counts[symbol].get(our_interval, 0) + 1
                
                # Print enhanced status display
                self.print_enhanced_status()
                    
            except websockets.ConnectionClosed:
                # Silently handle reconnection (shown in status display)
                self.stats['reconnections'] += 1
                break
            except Exception as e:
                # Only show errors in status display to keep terminal clean
                self.stats['errors'] += 1
                # Continue processing next message
    
    async def check_timeframe_gaps(self, symbol: str, interval: str, current_time: datetime) -> bool:
        """Check for gaps in timeframe data and handle missing candles.
        
        Args:
            symbol: Trading pair symbol
            interval: Timeframe interval ('1m', '1h', '1d')
            current_time: Current candle timestamp
            
        Returns:
            bool: True if gaps were found and handled, False otherwise
        """
        try:
            # Get existing data
            history_key = f"crypto:{symbol}:{interval}:history"
            last_candle_data = await self.redis.lrange(history_key, -1, -1)
            
            if not last_candle_data:
                return False  # No existing data to check gaps against
                
            last_candle = json.loads(last_candle_data[0])
            last_time = pd.to_datetime(last_candle['timestamp'])
            
            # Calculate time difference
            time_diff = current_time - last_time
            
            # Define expected intervals
            interval_timedelta = {
                '1m': timedelta(minutes=1),
                '1h': timedelta(hours=1),
                '1d': timedelta(days=1)
            }[interval]
            
            # Check if we missed any candles
            if time_diff > interval_timedelta * 2:  # If we missed more than one candle
                missed_candles = (time_diff // interval_timedelta) - 1
                # Silently log the gap for monitoring (no print to avoid cluttering display)
                
                # Add to gaps tracking
                if symbol not in self.stats['data_gaps']:
                    self.stats['data_gaps'][symbol] = []
                
                self.stats['data_gaps'][symbol].append({
                    'interval': interval,
                    'gap_size': time_diff.total_seconds() / 60,  # Gap in minutes
                    'last_update': last_time.isoformat(),
                    'current_time': current_time.isoformat(),
                    'missed_candles': int(missed_candles)
                })
                
                return True
                
            return False
            
        except Exception as e:
            print(f"Error checking timeframe gaps for {symbol} {interval}: {str(e)}")
            return False

    async def process_kline(self, symbol: str, interval: str, kline: dict):
        """Process a single kline/candlestick."""
        process_start = time.time()
        try:
            # Create DataFrame from kline data
            df = pd.DataFrame([{
                'timestamp': pd.to_datetime(kline['t'], unit='ms'),
                'open': float(kline['o']),
                'high': float(kline['h']),
                'low': float(kline['l']),
                'close': float(kline['c']),
                'volume': float(kline['v']),
                'close_time': kline['T'],
                'quote_asset_volume': float(kline['q']),
                'number_of_trades': int(kline['n']),
                'taker_buy_base_asset_volume': float(kline['V']),
                'taker_buy_quote_asset_volume': float(kline['Q'])
            }])
            
            # Data validation checks
            if not (float(kline['l']) <= float(kline['c']) <= float(kline['h']) and 
                   float(kline['l']) <= float(kline['o']) <= float(kline['h'])):
                print(f"Warning: Price integrity check failed for {symbol} {interval}")
                self.stats['errors'] += 1
                return

            # Only process completed candles
            if not kline['x']:  # If candle is not closed
                return
                
            # Check for timeframe gaps
            current_time = pd.to_datetime(kline['t'], unit='ms')
            gaps_found = await self.check_timeframe_gaps(symbol, interval, current_time)
            
            if gaps_found:
                # Silently track the gap (no print to avoid cluttering display)
                pass
            
            # Calculate indicators
            df = calculate_emas(df)
            df = calculate_volume_metrics(df)
            
            # Update Redis
            redis_start = time.time()
            await self.update_redis(symbol, interval, df)
            self.stats['redis_latency'].append(time.time() - redis_start)
            
            # Update last kline time
            key = f"{symbol}:{interval}"
            self.last_kline_update[key] = current_time
            
            # Update statistics
            self.stats['messages_processed'] += 1
            self.stats['updates_by_interval'][interval] += 1
            self.stats['processing_times'].append(time.time() - process_start)
            self.stats['last_update_time'] = time.time()
            
            # Update next refresh time (set to 1 minute from now for 1m interval)
            if interval == '1m':
                self.stats['next_refresh_time'] = datetime.now() + timedelta(minutes=1)
            
            # Silently process updates (no print to avoid cluttering the enhanced display)
        
        except KeyError as e:
            print(f"Missing key in kline data for {symbol} {interval}: {str(e)}")
            print(f"Kline data: {kline}")
            self.stats['errors'] += 1
        except ValueError as e:
            print(f"Value error processing kline for {symbol} {interval}: {str(e)}")
            self.stats['errors'] += 1
        except Exception as e:
            print(f"Unexpected error processing kline for {symbol} {interval}: {str(e)}")
            print(f"Kline data: {kline}")
            self.stats['errors'] += 1
            self.stats['last_error'] = {
                'time': datetime.now().isoformat(),
                'error': str(e),
                'symbol': symbol,
                'interval': interval
            }
    
    async def update_redis(self, symbol: str, interval: str, df: pd.DataFrame):
        """Update Redis with new candle data.
        
        Maintains a continuous historical record of all candles without trimming.
        Preserves all historical data collected from both data collector and websocket feeds.
        """
        try:
            # Prepare the new candle data
            record_dict = df.iloc[-1].to_dict()
            record_dict['timestamp'] = record_dict['timestamp'].isoformat()
            candle_time = pd.to_datetime(record_dict['timestamp'])
            
            # Key for historical data
            history_key = f"crypto:{symbol}:{interval}:history"
            
            # Get existing data to check for duplicates
            existing_data = await self.redis.lrange(history_key, -1, -1)
            
            if existing_data:
                last_candle = json.loads(existing_data[0])
                last_time = pd.to_datetime(last_candle['timestamp'])
                
                # Only add if this is a newer candle
                if candle_time > last_time:
                    # Add new record to history
                    await self.redis.rpush(history_key, json.dumps(record_dict))
                    
                    # Don't trim historical data - preserve all collected data
                    # Set a longer expiration to prevent accidental data loss
                    await self.redis.expire(history_key, 365 * 24 * 60 * 60)  # Expire after 1 year
            else:
                # First entry for this symbol/interval
                await self.redis.rpush(history_key, json.dumps(record_dict))
            
        except Exception as e:
            print(f"Error updating Redis for {symbol} {interval}: {str(e)}")
            self.stats['redis_errors'] += 1
            
    async def monitor_connection(self):
        """Monitor WebSocket connection and data freshness."""
        
        while self.running:
            try:
                current_time = datetime.now()
                
                # Check last update times and data freshness
                missing_updates = []
                for symbol in self.symbols:
                    for interval in ['1m', '1h', '1d']:
                        key = f"{symbol}:{interval}"
                        last_update = self.last_kline_update.get(key)
                        
                        if last_update:
                            time_diff = current_time - last_update
                            max_delay = timedelta(minutes=2 if interval == '1m' else 60)
                            
                            if time_diff > max_delay:
                                missing_updates.append({
                                    'symbol': symbol,
                                    'interval': interval,
                                    'last_update': last_update.isoformat(),
                                    'delay_minutes': time_diff.total_seconds() / 60
                                })

                # Check Redis connection
                try:
                    await self.redis.ping()
                except Exception as e:
                    print(f"Warning: Redis connection error: {str(e)}")
                    self.stats['redis_errors'] += 1
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                print(f"Error in connection monitor: {str(e)}")
                await asyncio.sleep(5)

    async def run_periodic_tasks(self):
        """Run periodic tasks."""
        while self.running:
            try:
                # Keep alive - can add other periodic tasks here if needed
                await asyncio.sleep(60)  # Check every minute
            except Exception as e:
                print(f"Error in periodic tasks: {str(e)}")
                await asyncio.sleep(60)

    async def get_historical_data(self, symbol: str, interval: str) -> pd.DataFrame:
        """Get historical data for a symbol and interval from Redis only.
        
        Args:
            symbol: Trading pair symbol (e.g., 'BTCUSDT')
            interval: Timeframe ('1m', '1h', '1d')
            
        Returns:
            DataFrame with historical candle data from Redis
        """
        try:
            history_key = f"crypto:{symbol}:{interval}:history"
            data = await self.redis.lrange(history_key, 0, -1)
            
            if not data:
                return pd.DataFrame()
            
            # Convert JSON strings to dictionaries
            candles = [json.loads(item) for item in data]
            
            # Create DataFrame
            df = pd.DataFrame(candles)
            
            # Convert timestamp strings back to datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Sort by timestamp to ensure proper order
            df = df.sort_values('timestamp')
            
            return df
            
        except Exception as e:
            print(f"Error retrieving historical data for {symbol} {interval}: {str(e)}")
            return pd.DataFrame()
        
async def main():
    """Main function to run the WebSocket manager."""
    try:
        manager = BinanceWebSocketManager()
        
        # Initialize Redis connection first
        redis = await connect_to_redis()
        if not redis:
            raise Exception("Failed to establish Redis connection")
        
        # Set the manager's redis connection
        manager.redis = redis
        
        # Fill any gaps before starting live collection
        await manager.fill_gaps_on_startup()
        
        # Create tasks for connection and monitoring
        connection_task = asyncio.create_task(manager.connect())
        monitor_task = asyncio.create_task(manager.monitor_connection())
        periodic_task = asyncio.create_task(manager.run_periodic_tasks())
        
        try:
            # Run all tasks concurrently
            await asyncio.gather(connection_task, monitor_task, periodic_task)
        except asyncio.CancelledError:
            print("\nTasks cancelled. Starting cleanup...")
        except Exception as e:
            print(f"Error in main loop: {str(e)}")
            print(f"Error details:\n{traceback.format_exc()}")
        finally:
            # Close all WebSocket connections
            print("Closing WebSocket connections...")
            for ws in manager.websockets.values():
                if ws:
                    try:
                        await asyncio.shield(ws.close())
                    except Exception as e:
                        print(f"Error closing WebSocket: {e}")
            
            # Wait a moment for connections to finish closing
            await asyncio.sleep(0.5)
            
            # Clear websockets to prevent further access
            manager.websockets.clear()
            
            # Close Redis connection
            if redis:
                try:
                    await asyncio.wait_for(redis.aclose(), timeout=2.0)
                    print("Redis connection closed")
                except Exception as e:
                    print(f"Error closing Redis: {e}")
            
    except Exception as e:
        print(f"Fatal error in main: {str(e)}")
        print(f"Error details:\n{traceback.format_exc()}")
        raise  # Re-raise to trigger proper shutdown sequence

async def shutdown(manager, loop):
    """Perform graceful shutdown."""
    try:
        print("\nInitiating graceful shutdown...")
        print("Waiting for running tasks to complete...")
        
        # Stop the manager and set flag to prevent new tasks
        if manager:
            manager.running = False
            
        # Get current task and running tasks
        current_task = asyncio.current_task(loop)
        running_tasks = [t for t in asyncio.all_tasks(loop) 
                        if t is not current_task and not t.done()]
        
        # First, close WebSocket connections with proper cleanup
        if manager and manager.websockets:
            print("Closing WebSocket connections...")
            close_ws_tasks = []
            for conn_id, ws in list(manager.websockets.items()):
                if ws:
                    try:
                        close_ws_tasks.append(
                            asyncio.create_task(
                                asyncio.wait_for(ws.close(), timeout=2.0)
                            )
                        )
                    except (asyncio.TimeoutError, RuntimeError) as e:
                        print(f"Error during WebSocket cleanup for {conn_id}: {e}")
                    except Exception as e:
                        print(f"Unexpected error for connection {conn_id}: {e}")
            # Wait for all WebSocket close tasks together
            if close_ws_tasks:
                try:
                    await asyncio.gather(*close_ws_tasks, return_exceptions=True)
                except Exception as e:
                    print(f"Error during WebSocket closure: {e}")
            # Clear websockets dictionary
            manager.websockets.clear()
        
        # Close Redis connection if it exists
        if manager and manager.redis:
            print("Closing Redis connection...")
            try:
                # Use aclose() instead of close()
                await asyncio.wait_for(manager.redis.aclose(), timeout=2.0)
                manager.redis = None
                print("Redis connection closed")
            except Exception as e:
                print(f"Error closing Redis connection: {e}")
        
        # Now wait for remaining tasks to complete
        if running_tasks:
            print(f"Waiting for {len(running_tasks)} tasks to complete...")
            try:
                done, pending = await asyncio.wait(
                    running_tasks, 
                    timeout=5.0,
                    return_when=asyncio.ALL_COMPLETED
                )
                if pending:
                    print(f"Cancelling {len(pending)} pending tasks...")
                    for task in pending:
                        if not task.done():
                            task.cancel()
                    # Give cancelled tasks a moment to clean up
                    await asyncio.wait(pending, timeout=1.0)
            except Exception as e:
                print(f"Error waiting for tasks: {e}")
        
        # Print final statistics before exit
        if manager:
            try:
                print("\nFinal Statistics:")
                uptime = time.time() - manager.stats['start_time']
                print(f"Uptime: {uptime // 3600:.0f}h {uptime % 3600 // 60:.0f}m {uptime % 60:.0f}s")
                print(f"Messages received: {manager.stats['messages_received']}")
                print(f"Messages processed: {manager.stats['messages_processed']}")
                print(f"Errors: {manager.stats['errors']}")
                print(f"Redis errors: {manager.stats['redis_errors']}")
                print(f"Reconnections: {manager.stats['reconnections']}")
            except Exception as e:
                print(f"Error printing final statistics: {e}")
        
        print("\nShutdown complete!")
        
    except Exception as e:
        print(f"\nError during shutdown: {e}")
        print(f"Shutdown error details:\n{traceback.format_exc()}")
    finally:
        try:
            # Cancel all tasks except current, only if loop is running
            if not loop.is_closed() and loop.is_running():
                tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task(loop)]
                for task in tasks:
                    task.cancel()
                if tasks:
                    try:
                        await asyncio.wait(tasks, timeout=5.0)
                    except Exception:
                        pass

            # Only call shutdown_asyncgens if loop is not closed and not running tasks
            if not loop.is_closed() and (not loop.is_running() or not asyncio.all_tasks(loop)):
                try:
                    await loop.shutdown_asyncgens()
                except Exception as e:
                    print(f"Error during shutdown_asyncgens: {e}")

            # Final loop close
            if not loop.is_closed() and not loop.is_running():
                try:
                    loop.close()
                except Exception as e:
                    print(f"Error closing loop: {e}")
        except Exception as e:
            print(f"Error in final cleanup: {e}")

if __name__ == "__main__":
    manager = None
    loop = None
    shutdown_event = None
    
    async def graceful_shutdown():
        """Handle graceful shutdown of all components."""
        if manager:
            manager.running = False
        await shutdown(manager, loop)
    
    def handle_shutdown():
        """Handle shutdown signal."""
        if not shutdown_event.is_set():
            print("\nReceived shutdown signal, finishing current tasks...")
            shutdown_event.set()
            if not loop.is_closed():
                loop.create_task(graceful_shutdown())
    
    try:
        # Create the event loop and shutdown event
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        shutdown_event = asyncio.Event()
        
        # Create manager instance
        manager = BinanceWebSocketManager()
        
        # Set up signal handlers
        if sys.platform != 'win32':
            loop.add_signal_handler(signal.SIGINT, handle_shutdown)
            loop.add_signal_handler(signal.SIGTERM, handle_shutdown)
        else:
            signal.signal(signal.SIGINT, lambda s, f: handle_shutdown())
            signal.signal(signal.SIGTERM, lambda s, f: handle_shutdown())
        
        try:
            # Run main loop
            loop.run_until_complete(main())
        except asyncio.CancelledError:
            print("\nMain task cancelled, starting cleanup...")
        except KeyboardInterrupt:
            print("\nShutdown initiated by keyboard interrupt...")
        except Exception as e:
            print(f"\nError in main loop: {str(e)}")
            print(f"Error details:\n{traceback.format_exc()}")
        finally:
            # Stop the loop before cleanup
            try:
                loop.stop()
            except Exception as e:
                print(f"Error stopping event loop: {e}")
    except Exception as e:
        print(f"Fatal error during setup: {str(e)}")
        print(f"Setup error details:\n{traceback.format_exc()}")
    finally:
        try:
            # Always attempt graceful shutdown
            if not shutdown_event.is_set() and not loop.is_closed():
                # If the loop is running, schedule graceful_shutdown as a task
                if loop.is_running():
                    loop.create_task(graceful_shutdown())
                else:
                    loop.run_until_complete(graceful_shutdown())

            # Clean up signal handlers
            if sys.platform != 'win32' and not loop.is_closed():
                for sig in (signal.SIGINT, signal.SIGTERM):
                    try:
                        loop.remove_signal_handler(sig)
                    except:
                        pass

            # Final cleanup
            if not loop.is_closed():
                try:
                    # Only attempt to cancel tasks if the loop is running
                    if loop.is_running():
                        # Avoid calling asyncio.all_tasks/current_task if loop is not running
                        pass  # No-op, can't safely cancel tasks if loop is not running
                    else:
                        # Cancel all tasks first
                        try:
                            tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
                        except RuntimeError:
                            tasks = []
                        for task in tasks:
                            task.cancel()

                        if tasks:
                            try:
                                loop.run_until_complete(asyncio.wait(tasks, timeout=5.0))
                            except Exception:
                                pass

                        try:
                            loop.run_until_complete(loop.shutdown_asyncgens())
                        except Exception as e:
                            print(f"Error during final cleanup: {e}")
                        finally:
                            try:
                                loop.close()
                            except Exception as e:
                                print(f"Error closing event loop: {e}")
                except Exception as e:
                    print(f"Error during final cleanup: {e}")

            # Force garbage collection
            gc.collect()

        except Exception as e:
            print(f"Error during shutdown cleanup: {e}")
            print(f"Cleanup error details:\n{traceback.format_exc()}")
