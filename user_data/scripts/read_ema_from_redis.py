#!/usr/bin/env python3
"""
Redis EMA Data Reader
====================

Simple script to read and display EMA data from Redis.

Usage:
    python read_ema_from_redis.py [symbol]
    
Examples:
    python read_ema_from_redis.py
    python read_ema_from_redis.py BTC/USDT
"""

import sys
import json
import redis
from datetime import datetime


def connect_redis():
    """Connect to Redis"""
    try:
        client = redis.Redis(host='localhost', port=6379, db=1, decode_responses=True)
        client.ping()
        return client
    except redis.ConnectionError as e:
        print(f"❌ Failed to connect to Redis: {e}")
        print("Make sure Redis is running: docker-compose ps")
        sys.exit(1)


def list_available_data(redis_client):
    """List all available symbols and timeframes in Redis"""
    keys = redis_client.keys("ema_data:*")
    # Filter main data keys (not individual EMA or signal keys)
    main_keys = [key for key in keys if not any(x in key for x in [':ema_', ':signals', ':price', ':last_update'])]
    
    data_map = {}
    for key in main_keys:
        # Parse key: ema_data:BTC_USDT:1h -> symbol: BTC/USDT, timeframe: 1h
        parts = key.split(':')
        if len(parts) >= 3:
            symbol = parts[1].replace('_', '/')
            timeframe = parts[2]
            
            if symbol not in data_map:
                data_map[symbol] = []
            data_map[symbol].append(timeframe)
    
    # Sort symbols and timeframes
    for symbol in data_map:
        data_map[symbol] = sorted(data_map[symbol], key=lambda x: {
            '1m': 1, '5m': 2, '15m': 3, '30m': 4, 
            '1h': 5, '4h': 6, '1d': 7, '1w': 8
        }.get(x, 999))
    
    return data_map


def get_ema_data(redis_client, symbol, timeframe='1h'):
    """Get EMA data for a specific symbol and timeframe"""
    key = f"ema_data:{symbol.replace('/', '_')}:{timeframe}"
    
    try:
        data = redis_client.get(key)
        if data:
            return json.loads(data)
        else:
            return None
    except Exception as e:
        print(f"❌ Error retrieving data for {symbol} {timeframe}: {e}")
        return None


def display_ema_data(data):
    """Display EMA data in a nice format"""
    if not data:
        return
    
    symbol = data['symbol']
    timeframe = data['timeframe']
    price = data['last_price']
    timestamp = data['timestamp']
    
    print(f"\n📊 {symbol} - {timeframe}")
    print("=" * 50)
    print(f"Current Price: ${price:.4f}")
    print(f"Last Update: {timestamp}")
    
    if 'candle_data' in data:
        candle = data['candle_data']
        print(f"OHLCV: O:${candle['open']:.4f} H:${candle['high']:.4f} "
              f"L:${candle['low']:.4f} C:${candle['close']:.4f} V:{candle['volume']:.0f}")
    
    print(f"\n📈 EMA Values:")
    for ema_key, ema_info in data['emas'].items():
        period = ema_key.split('_')[1]
        value = ema_info['value']
        trend = ema_info['trend']
        trend_emoji = "📈" if trend == 'up' else "📉"
        
        # Calculate distance from current price
        distance_pct = ema_info.get('price_distance_pct', 0)
        distance_str = f"({distance_pct:+.2f}%)"
        
        print(f"  EMA-{period:>3}: ${value:>10.4f} {trend_emoji} {distance_str}")
    
    if data['signals']:
        print(f"\n🎯 Trading Signals:")
        for signal_key, signal_value in data['signals'].items():
            if signal_value is not None:
                emoji = "✅" if signal_value else "❌"
                signal_name = signal_key.replace('_', ' ').title()
                print(f"  {signal_name}: {emoji}")


def show_market_overview(redis_client):
    """Show market overview across all timeframes"""
    data_map = list_available_data(redis_client)
    
    if not data_map:
        print("❌ No EMA data found in Redis.")
        return
    
    print(f"\n📈 MARKET OVERVIEW")
    print("=" * 60)
    
    # Get all timeframes
    all_timeframes = set()
    for symbol_timeframes in data_map.values():
        all_timeframes.update(symbol_timeframes)
    
    timeframes = sorted(all_timeframes, key=lambda x: {
        '1m': 1, '5m': 2, '15m': 3, '30m': 4, 
        '1h': 5, '4h': 6, '1d': 7, '1w': 8
    }.get(x, 999))
    
    for timeframe in timeframes:
        bullish_count = 0
        bearish_count = 0
        mixed_count = 0
        total_count = 0
        
        for symbol in data_map:
            if timeframe in data_map[symbol]:
                data = get_ema_data(redis_client, symbol, timeframe)
                if data and data['signals']:
                    total_count += 1
                    if data['signals'].get('bullish_alignment'):
                        bullish_count += 1
                    elif data['signals'].get('bearish_alignment'):
                        bearish_count += 1
                    else:
                        mixed_count += 1
        
        if total_count > 0:
            bullish_pct = (bullish_count / total_count) * 100
            print(f"{timeframe:>4}: 🟢{bullish_count:>2} 🔴{bearish_count:>2} 🟡{mixed_count:>2} | "
                  f"Bullish: {bullish_pct:.0f}% ({total_count} pairs)")
    
    print("=" * 60)


def main():
    """Main function"""
    print("📖 Multi-Timeframe Redis EMA Data Reader")
    print("=" * 60)
    
    # Connect to Redis
    redis_client = connect_redis()
    
    # Get available data
    data_map = list_available_data(redis_client)
    
    if not data_map:
        print("❌ No EMA data found in Redis.")
        print("Run 'python ema_to_redis.py' first to generate data.")
        return
    
    # Show market overview first
    show_market_overview(redis_client)
    
    # Determine what to show based on command line arguments
    if len(sys.argv) >= 2:
        # Symbol specified as argument
        requested_symbol = sys.argv[1]
        requested_timeframe = sys.argv[2] if len(sys.argv) > 2 else '1h'
        
        if requested_symbol in data_map:
            if requested_timeframe in data_map[requested_symbol]:
                data = get_ema_data(redis_client, requested_symbol, requested_timeframe)
                if data:
                    display_ema_data(data)
                else:
                    print(f"❌ No data found for {requested_symbol} {requested_timeframe}")
            else:
                print(f"❌ Timeframe '{requested_timeframe}' not found for {requested_symbol}")
                print(f"Available timeframes: {', '.join(data_map[requested_symbol])}")
        else:
            print(f"❌ Symbol '{requested_symbol}' not found.")
            print(f"Available symbols: {', '.join(sorted(data_map.keys()))}")
    else:
        # Show summary for all symbols and timeframes
        print(f"\n📋 DETAILED DATA")
        print("=" * 60)
        
        count = 0
        for symbol in sorted(data_map.keys()):
            if count >= 5:  # Limit output to avoid spam
                remaining = len(data_map) - count
                print(f"\n... and {remaining} more symbols")
                break
                
            print(f"\n🪙 {symbol}")
            for timeframe in data_map[symbol][:3]:  # Show first 3 timeframes per symbol
                data = get_ema_data(redis_client, symbol, timeframe)
                if data:
                    price = data['last_price']
                    bullish = data['signals'].get('bullish_alignment', False)
                    bearish = data['signals'].get('bearish_alignment', False)
                    alignment = "🟢 Bullish" if bullish else "🔴 Bearish" if bearish else "🟡 Mixed"
                    
                    key_emas = []
                    for period in [7, 25, 50]:
                        ema_key = f'ema_{period}'
                        if ema_key in data['emas']:
                            distance = data['emas'][ema_key]['price_distance_pct']
                            key_emas.append(f"EMA{period}:{distance:+.1f}%")
                    
                    emas_str = " | ".join(key_emas)
                    print(f"  {timeframe:>4}: ${price:>8.4f} {alignment} | {emas_str}")
            
            count += 1
    
    print(f"\n✨ Use 'python read_ema_from_redis.py SYMBOL TIMEFRAME' for detailed view")
    print(f"Example: python read_ema_from_redis.py BTC/USDT 1h")
    print(f"Available symbols: {', '.join(sorted(data_map.keys()))}")
    available_timeframes = set()
    for symbol_timeframes in data_map.values():
        available_timeframes.update(symbol_timeframes)
    print(f"Available timeframes: {', '.join(sorted(available_timeframes))}")


if __name__ == "__main__":
    main()
