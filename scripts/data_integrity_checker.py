#!/usr/bin/env python3
"""
Redis Data Integrity Checker
Verifies consecutive timestamps in cryptocurrency candle data for all timeframes
"""

import asyncio
import redis.asyncio as aioredis
import json
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import sys
from colorama import Fore, Style, init
from binance.client import Client
import threading
from ta.trend import EMAIndicator

# Initialize colorama for colored output
init(autoreset=True)

# Thread-local storage for Binance client instances
thread_local = threading.local()

def get_thread_binance_client():
    """Get thread-local Binance client instance."""
    if not hasattr(thread_local, 'binance_client'):
        thread_local.binance_client = Client(
            None,  # API key
            None,  # API secret
            {"timeout": 15, "verify": True}
        )
    return thread_local.binance_client

def calculate_emas(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate EMAs for different periods."""
    periods = [7, 15, 25, 55, 99, 200, 300]
    
    for period in periods:
        if len(df) >= period:
            ema = EMAIndicator(close=df['close'], window=period)
            df[f'ema_{period}'] = ema.ema_indicator()
        else:
            df[f'ema_{period}'] = None
    
    return df

def calculate_volume_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate additional volume metrics."""
    df['total_volume'] = df['volume']
    df['buying_volume'] = df['taker_buy_base_asset_volume']
    df['selling_volume'] = df['volume'] - df['taker_buy_base_asset_volume']
    return df

class DataIntegrityChecker:
    def __init__(self):
        self.redis = None
        self.gaps_found = {}
        self.total_candles = {}
        self.gap_stats = {
            '1m': {'gaps': 0, 'missing_candles': 0},
            '1h': {'gaps': 0, 'missing_candles': 0},
            '1d': {'gaps': 0, 'missing_candles': 0}
        }
    
    async def connect_to_redis(self):
        """Connect to Redis database."""
        try:
            self.redis = aioredis.Redis(
                host='localhost',
                port=6379,
                db=0,
                decode_responses=True
            )
            await self.redis.ping()
            print(f"{Fore.GREEN}✅ Connected to Redis successfully!{Style.RESET_ALL}")
            return True
        except Exception as e:
            print(f"{Fore.RED}❌ Failed to connect to Redis: {e}{Style.RESET_ALL}")
            return False
    
    def get_expected_interval(self, timeframe: str) -> timedelta:
        """Get expected time interval for each timeframe."""
        intervals = {
            '1m': timedelta(minutes=1),
            '1h': timedelta(hours=1),
            '1d': timedelta(days=1)
        }
        return intervals[timeframe]
    
    def format_gap_info(self, gap_start: datetime, gap_end: datetime, timeframe: str) -> Dict:
        """Format gap information for reporting."""
        interval = self.get_expected_interval(timeframe)
        expected_candles = int((gap_end - gap_start) / interval)
        
        return {
            'start_time': gap_start.isoformat(),
            'end_time': gap_end.isoformat(),
            'duration': str(gap_end - gap_start),
            'missing_candles': expected_candles,
            'timeframe': timeframe
        }
    
    async def fetch_missing_data(self, symbol: str, timeframe: str, start_time: datetime, end_time: datetime) -> List[Dict]:
        """Fetch missing data from Binance API."""
        try:
            client = get_thread_binance_client()
            
            # Convert datetime to milliseconds
            start_ms = int(start_time.timestamp() * 1000)
            end_ms = int(end_time.timestamp() * 1000)
            
            print(f"  📥 Fetching data from {start_time.strftime('%Y-%m-%d %H:%M')} to {end_time.strftime('%Y-%m-%d %H:%M')}")
            
            # Fetch historical klines
            klines = client.get_historical_klines(
                symbol=symbol,
                interval=timeframe,
                start_str=str(start_ms),
                end_str=str(end_ms)
            )
            
            # Convert to our format
            candles = []
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
                candles.append(candle)
            
            return candles
            
        except Exception as e:
            print(f"  {Fore.RED}❌ Error fetching data: {e}{Style.RESET_ALL}")
            return []
    
    async def fill_gap(self, symbol: str, timeframe: str, gap_info: Dict) -> bool:
        """Fill a specific gap by fetching missing data and inserting it into Redis."""
        try:
            start_time = pd.to_datetime(gap_info['start_time'])
            end_time = pd.to_datetime(gap_info['end_time'])
            
            print(f"  🔧 Filling gap of {gap_info['missing_candles']} candles...")
            
            # Fetch missing data
            missing_candles = await self.fetch_missing_data(symbol, timeframe, start_time, end_time)
            
            if not missing_candles:
                print(f"  {Fore.RED}❌ No data received from Binance{Style.RESET_ALL}")
                return False
            
            # Process with technical indicators
            df = pd.DataFrame(missing_candles)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = calculate_emas(df)
            df = calculate_volume_metrics(df)
            
            # Get the history key
            history_key = f"crypto:{symbol}:{timeframe}:history"
            
            # Get all existing data to find insertion points
            existing_data = await self.redis.lrange(history_key, 0, -1)
            all_candles = []
            
            # Parse existing data
            for item in existing_data:
                candle = json.loads(item)
                candle['timestamp'] = pd.to_datetime(candle['timestamp'])
                all_candles.append(candle)
            
            # Add new candles
            for _, row in df.iterrows():
                candle_dict = row.to_dict()
                # Ensure timestamp is ISO string
                if isinstance(candle_dict['timestamp'], pd.Timestamp):
                    candle_dict['timestamp'] = candle_dict['timestamp'].isoformat()
                all_candles.append(candle_dict)

            # Sort all candles by timestamp
            all_candles.sort(key=lambda x: pd.to_datetime(x['timestamp']))

            # Convert all timestamps to ISO string for JSON serialization
            for candle in all_candles:
                if isinstance(candle['timestamp'], pd.Timestamp):
                    candle['timestamp'] = candle['timestamp'].isoformat()

            # Clear and rebuild the Redis list
            await self.redis.delete(history_key)

            # Insert all candles in correct order
            candle_jsons = [json.dumps(candle) for candle in all_candles]
            if candle_jsons:
                await self.redis.rpush(history_key, *candle_jsons)
                # Set expiration
                await self.redis.expire(history_key, 365 * 24 * 60 * 60)  # 1 year
            
            print(f"  {Fore.GREEN}✅ Filled gap with {len(missing_candles)} candles{Style.RESET_ALL}")
            return True
            
        except Exception as e:
            print(f"  {Fore.RED}❌ Error filling gap: {e}{Style.RESET_ALL}")
            return False
    
    async def fill_all_gaps_for_symbol(self, symbol: str, timeframe: str, gaps: List[Dict]) -> int:
        """Fill all gaps for a specific symbol and timeframe."""
        filled_count = 0
        
        print(f"\n{Fore.YELLOW}🔧 Filling {len(gaps)} gaps for {symbol} {timeframe}:{Style.RESET_ALL}")
        
        for i, gap in enumerate(gaps, 1):
            print(f"  Gap {i}/{len(gaps)}: {gap['missing_candles']} missing candles")
            
            success = await self.fill_gap(symbol, timeframe, gap)
            if success:
                filled_count += 1
            
            # Small delay to avoid overwhelming the API
            await asyncio.sleep(0.1)
        
        return filled_count
    
    async def run_full_integrity_check(self):
        """Run comprehensive integrity check on all data."""
        print(f"{Fore.CYAN}🔍 STARTING COMPREHENSIVE DATA INTEGRITY CHECK")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        
        # Get all symbols
        symbols = await self.get_all_symbols()
        if not symbols:
            print(f"{Fore.RED}❌ No symbols found in Redis!{Style.RESET_ALL}")
            return []
        
        print(f"{Fore.GREEN}📊 Found {len(symbols)} symbols to analyze{Style.RESET_ALL}")
        print(f"Symbols: {', '.join(symbols)}")
        
        timeframes = ['1m', '1h', '1d']
        all_results = []
        
        total_checks = len(symbols) * len(timeframes)
        completed = 0
        
        # Check each symbol and timeframe combination
        for symbol in symbols:
            for timeframe in timeframes:
                completed += 1
                progress = (completed / total_checks) * 100
                
                print(f"\n[{completed}/{total_checks}] {progress:.1f}% - Checking {symbol} {timeframe}...", end=" ")
                
                result = await self.check_symbol_integrity(symbol, timeframe)
                all_results.append(result)
                
                # Print immediate status
                status = result['status']
                if status == 'INTACT':
                    print(f"{Fore.GREEN}✅ INTACT ({result['total_candles']} candles){Style.RESET_ALL}")
                elif status == 'GAPS_FOUND':
                    gap_count = len(result['gaps'])
                    missing = sum(gap['missing_candles'] for gap in result['gaps'])
                    print(f"{Fore.YELLOW}⚠️  {gap_count} GAPS ({missing} missing candles){Style.RESET_ALL}")
                elif status == 'NO_DATA':
                    print(f"{Fore.LIGHTBLACK_EX}📭 NO DATA{Style.RESET_ALL}")
                elif status == 'ERROR':
                    print(f"{Fore.RED}❌ ERROR{Style.RESET_ALL}")
                
                # Print gap details for symbols with issues
                if status == 'GAPS_FOUND' and len(result['gaps']) <= 5:  # Only show details for few gaps
                    self.print_gap_details(result)
        
        # Print comprehensive summary
        self.print_summary_report(all_results)
        
        # Save detailed report to file
        await self.save_detailed_report(all_results)
        
        return all_results
        """Format gap information for reporting."""
        interval = self.get_expected_interval(timeframe)
        expected_candles = int((gap_end - gap_start) / interval)
        
        return {
            'start_time': gap_start.isoformat(),
            'end_time': gap_end.isoformat(),
            'duration': str(gap_end - gap_start),
            'missing_candles': expected_candles,
            'timeframe': timeframe
        }
    
    async def check_symbol_integrity(self, symbol: str, timeframe: str) -> Dict:
        """Check data integrity for a specific symbol and timeframe."""
        try:
            # Get all historical data for this symbol/timeframe
            history_key = f"crypto:{symbol}:{timeframe}:history"
            data = await self.redis.lrange(history_key, 0, -1)
            
            if not data:
                return {
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'status': 'NO_DATA',
                    'total_candles': 0,
                    'gaps': [],
                    'first_candle': None,
                    'last_candle': None
                }
            
            # Parse candles and sort by timestamp
            candles = []
            for item in data:
                try:
                    candle = json.loads(item)
                    candle['timestamp'] = pd.to_datetime(candle['timestamp'])
                    candles.append(candle)
                except json.JSONDecodeError:
                    print(f"{Fore.YELLOW}⚠️  Warning: Invalid JSON in {symbol} {timeframe}{Style.RESET_ALL}")
                    continue
            
            # Sort by timestamp
            candles.sort(key=lambda x: x['timestamp'])
            
            if not candles:
                return {
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'status': 'INVALID_DATA',
                    'total_candles': 0,
                    'gaps': [],
                    'first_candle': None,
                    'last_candle': None
                }
            
            # Check for gaps
            gaps = []
            expected_interval = self.get_expected_interval(timeframe)
            
            for i in range(1, len(candles)):
                current_time = candles[i]['timestamp']
                previous_time = candles[i-1]['timestamp']
                
                # Calculate expected next timestamp
                expected_time = previous_time + expected_interval
                
                # If there's a gap larger than the expected interval
                if current_time > expected_time:
                    gap_info = self.format_gap_info(previous_time + expected_interval, current_time, timeframe)
                    gaps.append(gap_info)
                    
                    # Update statistics
                    self.gap_stats[timeframe]['gaps'] += 1
                    self.gap_stats[timeframe]['missing_candles'] += gap_info['missing_candles']
            
            # Calculate data coverage
            first_candle = candles[0]['timestamp']
            last_candle = candles[-1]['timestamp']
            total_duration = last_candle - first_candle
            expected_total_candles = int(total_duration / expected_interval) + 1
            actual_candles = len(candles)
            coverage_percentage = (actual_candles / expected_total_candles) * 100 if expected_total_candles > 0 else 0
            
            return {
                'symbol': symbol,
                'timeframe': timeframe,
                'status': 'GAPS_FOUND' if gaps else 'INTACT',
                'total_candles': len(candles),
                'expected_candles': expected_total_candles,
                'coverage_percentage': coverage_percentage,
                'gaps': gaps,
                'first_candle': first_candle.isoformat(),
                'last_candle': last_candle.isoformat(),
                'duration': str(total_duration)
            }
            
        except Exception as e:
            print(f"{Fore.RED}❌ Error checking {symbol} {timeframe}: {e}{Style.RESET_ALL}")
            return {
                'symbol': symbol,
                'timeframe': timeframe,
                'status': 'ERROR',
                'error': str(e),
                'total_candles': 0,
                'gaps': [],
                'first_candle': None,
                'last_candle': None
            }
    
    async def get_all_symbols(self) -> List[str]:
        """Get all symbols that have data in Redis."""
        try:
            keys = await self.redis.keys('crypto:*:*:history')
            symbols = set()
            return ['XRPUSDT', 'LTCUSDT', 'SUSHIUSDT', 'EPICUSDT', 'LOKAUSDT']
        except Exception as e:
            print(f"{Fore.RED}❌ Error getting symbols: {e}{Style.RESET_ALL}")
            return []
    
    def print_gap_details(self, result: Dict):
        """Print detailed gap information for a symbol/timeframe."""
        symbol = result['symbol']
        timeframe = result['timeframe']
        gaps = result['gaps']
        
        if not gaps:
            return
        
        print(f"\n{Fore.YELLOW}📋 Gap Details for {symbol} {timeframe}:{Style.RESET_ALL}")
        for i, gap in enumerate(gaps, 1):
            start_time = pd.to_datetime(gap['start_time'])
            end_time = pd.to_datetime(gap['end_time'])
            
            print(f"  {Fore.RED}Gap #{i}:{Style.RESET_ALL}")
            print(f"    Start: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"    End:   {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"    Duration: {gap['duration']}")
            print(f"    Missing candles: {gap['missing_candles']}")
    
    def print_summary_report(self, all_results: List[Dict]):
        """Print a comprehensive summary report."""
        print(f"\n{Fore.CYAN}{'='*80}")
        print(f"{Fore.CYAN}📊 DATA INTEGRITY SUMMARY REPORT")
        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")
        
        # Group results by timeframe
        timeframe_results = {'1m': [], '1h': [], '1d': []}
        for result in all_results:
            tf = result['timeframe']
            if tf in timeframe_results:
                timeframe_results[tf].append(result)
        
        for timeframe in ['1m', '1h', '1d']:
            results = timeframe_results[timeframe]
            if not results:
                continue
                
            print(f"\n{Fore.WHITE}⏰ {timeframe.upper()} TIMEFRAME ANALYSIS:{Style.RESET_ALL}")
            
            intact_count = len([r for r in results if r['status'] == 'INTACT'])
            gaps_count = len([r for r in results if r['status'] == 'GAPS_FOUND'])
            error_count = len([r for r in results if r['status'] == 'ERROR'])
            no_data_count = len([r for r in results if r['status'] == 'NO_DATA'])
            
            print(f"  Symbols analyzed: {len(results)}")
            print(f"  {Fore.GREEN}✅ Intact: {intact_count}{Style.RESET_ALL}")
            print(f"  {Fore.YELLOW}⚠️  With gaps: {gaps_count}{Style.RESET_ALL}")
            print(f"  {Fore.RED}❌ Errors: {error_count}{Style.RESET_ALL}")
            print(f"  {Fore.LIGHTBLACK_EX}📭 No data: {no_data_count}{Style.RESET_ALL}")
            
            if self.gap_stats[timeframe]['gaps'] > 0:
                print(f"  Total gaps found: {self.gap_stats[timeframe]['gaps']}")
                print(f"  Total missing candles: {self.gap_stats[timeframe]['missing_candles']}")
            
            # Show symbols with gaps
            gap_symbols = [r for r in results if r['status'] == 'GAPS_FOUND']
            if gap_symbols:
                print(f"\n  {Fore.YELLOW}Symbols with gaps:{Style.RESET_ALL}")
                for result in gap_symbols:
                    symbol = result['symbol']
                    gap_count = len(result['gaps'])
                    missing = sum(gap['missing_candles'] for gap in result['gaps'])
                    coverage = result.get('coverage_percentage', 0)
                    print(f"    {symbol}: {gap_count} gaps, {missing} missing candles, {coverage:.1f}% coverage")
    
    async def run_gap_filling_mode(self):
        """Run in gap filling mode - detect and fill all gaps."""
        print(f"{Fore.CYAN}🔧 STARTING GAP FILLING MODE")
        print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
        
        # Get all symbols
        symbols = await self.get_all_symbols()
        if not symbols:
            print(f"{Fore.RED}❌ No symbols found in Redis!{Style.RESET_ALL}")
            return
        
        print(f"{Fore.GREEN}📊 Found {len(symbols)} symbols to analyze and fill{Style.RESET_ALL}")
        print(f"Symbols: {', '.join(symbols)}")
        
        timeframes = ['1m', '1h', '1d']
        total_gaps_filled = 0
        total_gaps_found = 0
        
        # Process each symbol and timeframe
        for symbol in symbols:
            for timeframe in timeframes:
                print(f"\n{Fore.WHITE}🔍 Analyzing {symbol} {timeframe}...{Style.RESET_ALL}")
                
                # Check for gaps
                result = await self.check_symbol_integrity(symbol, timeframe)
                
                if result['status'] == 'GAPS_FOUND':
                    gaps = result['gaps']
                    total_gaps_found += len(gaps)
                    
                    print(f"  {Fore.YELLOW}⚠️  Found {len(gaps)} gaps with {sum(g['missing_candles'] for g in gaps)} missing candles{Style.RESET_ALL}")
                    
                    # Ask user if they want to fill gaps for this symbol/timeframe
                    if len(gaps) > 10:
                        print(f"  {Fore.YELLOW}⚠️  This symbol has many gaps ({len(gaps)}). Fill all? (y/n/s for skip): {Style.RESET_ALL}", end="")
                        choice = input().strip().lower()
                        if choice == 'n':
                            continue
                        elif choice == 's':
                            print(f"  {Fore.LIGHTBLACK_EX}⏭️  Skipping {symbol} {timeframe}{Style.RESET_ALL}")
                            continue
                    
                    # Fill the gaps
                    filled = await self.fill_all_gaps_for_symbol(symbol, timeframe, gaps)
                    total_gaps_filled += filled
                    
                    if filled == len(gaps):
                        print(f"  {Fore.GREEN}✅ All {filled} gaps filled successfully!{Style.RESET_ALL}")
                    else:
                        print(f"  {Fore.YELLOW}⚠️  Filled {filled}/{len(gaps)} gaps{Style.RESET_ALL}")
                
                elif result['status'] == 'INTACT':
                    print(f"  {Fore.GREEN}✅ No gaps found - data is intact{Style.RESET_ALL}")
                
                elif result['status'] == 'NO_DATA':
                    print(f"  {Fore.LIGHTBLACK_EX}📭 No data available{Style.RESET_ALL}")
                
                else:
                    print(f"  {Fore.RED}❌ Error analyzing data{Style.RESET_ALL}")
        
        # Final summary
        print(f"\n{Fore.CYAN}{'='*60}")
        print(f"{Fore.CYAN}📊 GAP FILLING SUMMARY")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"Total gaps found: {total_gaps_found}")
        print(f"Total gaps filled: {Fore.GREEN}{total_gaps_filled}{Style.RESET_ALL}")
        
        if total_gaps_filled == total_gaps_found:
            print(f"{Fore.GREEN}🎉 All gaps successfully filled!{Style.RESET_ALL}")
        elif total_gaps_filled > 0:
            print(f"{Fore.YELLOW}⚠️  {total_gaps_found - total_gaps_filled} gaps remain unfilled{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}❌ No gaps were filled{Style.RESET_ALL}")
        
        return total_gaps_filled
        """Run comprehensive integrity check on all data."""
        print(f"{Fore.CYAN}🔍 STARTING COMPREHENSIVE DATA INTEGRITY CHECK")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        
        # Get all symbols
        symbols = await self.get_all_symbols()
        if not symbols:
            print(f"{Fore.RED}❌ No symbols found in Redis!{Style.RESET_ALL}")
            return
        
        print(f"{Fore.GREEN}📊 Found {len(symbols)} symbols to analyze{Style.RESET_ALL}")
        print(f"Symbols: {', '.join(symbols)}")
        
        timeframes = ['1m', '1h', '1d']
        all_results = []
        
        total_checks = len(symbols) * len(timeframes)
        completed = 0
        
        # Check each symbol and timeframe combination
        for symbol in symbols:
            for timeframe in timeframes:
                completed += 1
                progress = (completed / total_checks) * 100
                
                print(f"\n[{completed}/{total_checks}] {progress:.1f}% - Checking {symbol} {timeframe}...", end=" ")
                
                result = await self.check_symbol_integrity(symbol, timeframe)
                all_results.append(result)
                
                # Print immediate status
                status = result['status']
                if status == 'INTACT':
                    print(f"{Fore.GREEN}✅ INTACT ({result['total_candles']} candles){Style.RESET_ALL}")
                elif status == 'GAPS_FOUND':
                    gap_count = len(result['gaps'])
                    missing = sum(gap['missing_candles'] for gap in result['gaps'])
                    print(f"{Fore.YELLOW}⚠️  {gap_count} GAPS ({missing} missing candles){Style.RESET_ALL}")
                elif status == 'NO_DATA':
                    print(f"{Fore.LIGHTBLACK_EX}📭 NO DATA{Style.RESET_ALL}")
                elif status == 'ERROR':
                    print(f"{Fore.RED}❌ ERROR{Style.RESET_ALL}")
                
                # Print gap details for symbols with issues
                if status == 'GAPS_FOUND' and len(result['gaps']) <= 5:  # Only show details for few gaps
                    self.print_gap_details(result)
        
        # Print comprehensive summary
        self.print_summary_report(all_results)
        
        # Save detailed report to file
        await self.save_detailed_report(all_results)
        
        return all_results
    
    async def save_detailed_report(self, results: List[Dict]):
        """Save detailed integrity report to file."""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"data_integrity_report_{timestamp}.json"
            
            report = {
                'timestamp': datetime.now().isoformat(),
                'summary': self.gap_stats,
                'detailed_results': results
            }
            
            with open(filename, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            print(f"\n{Fore.GREEN}💾 Detailed report saved to: {filename}{Style.RESET_ALL}")
            
        except Exception as e:
            print(f"{Fore.RED}❌ Error saving report: {e}{Style.RESET_ALL}")

async def main():
    """Main function."""
    print(f"{Fore.CYAN}🔍 REDIS DATA INTEGRITY CHECKER & GAP FILLER")
    print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
    
    checker = DataIntegrityChecker()
    
    # Connect to Redis
    if not await checker.connect_to_redis():
        print(f"{Fore.RED}❌ Cannot proceed without Redis connection{Style.RESET_ALL}")
        return
    
    try:
        # Ask user what they want to do
        print(f"\n{Fore.WHITE}Choose operation:{Style.RESET_ALL}")
        print(f"1. {Fore.YELLOW}Check integrity only{Style.RESET_ALL} (detect gaps)")
        print(f"2. {Fore.GREEN}Fill gaps{Style.RESET_ALL} (detect and fill missing data)")
        print(f"3. {Fore.CYAN}Both{Style.RESET_ALL} (check first, then fill)")
        
        choice = input(f"\nEnter choice (1/2/3): ").strip()
        
        if choice == '1':
            # Run integrity check only
            results = await checker.run_full_integrity_check()
            
        elif choice == '2':
            # Run gap filling mode
            await checker.run_gap_filling_mode()
            
        elif choice == '3':
            # Run both - check first, then fill
            print(f"\n{Fore.CYAN}Step 1: Running integrity check...{Style.RESET_ALL}")
            results = await checker.run_full_integrity_check()
            
            # Count total gaps
            total_gaps = sum(len(r.get('gaps', [])) for r in results if r.get('status') == 'GAPS_FOUND')
            
            if total_gaps > 0:
                print(f"\n{Fore.YELLOW}Found {total_gaps} total gaps. Proceed with filling? (y/n): {Style.RESET_ALL}", end="")
                fill_choice = input().strip().lower()
                
                if fill_choice == 'y':
                    print(f"\n{Fore.CYAN}Step 2: Filling gaps...{Style.RESET_ALL}")
                    await checker.run_gap_filling_mode()
                else:
                    print(f"{Fore.YELLOW}Gap filling cancelled by user{Style.RESET_ALL}")
            else:
                print(f"\n{Fore.GREEN}✅ No gaps found - data integrity is perfect!{Style.RESET_ALL}")
        
        else:
            print(f"{Fore.RED}❌ Invalid choice{Style.RESET_ALL}")
        
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}👋 Operation cancelled by user{Style.RESET_ALL}")
    except Exception as e:
        print(f"\n{Fore.RED}❌ Unexpected error: {e}{Style.RESET_ALL}")
    finally:
        # Close Redis connection
        if checker.redis:
            await checker.redis.aclose()
            print(f"\n{Fore.GREEN}🔌 Disconnected from Redis{Style.RESET_ALL}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}👋 Goodbye!{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}❌ Fatal error: {e}{Style.RESET_ALL}")
        sys.exit(1)
