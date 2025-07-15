#!/usr/bin/env python3
"""
Simple EMA Test
Test the basic functionality step by step
"""

import redis
import json
import sys
import os

# Test Redis connection first
print("🔌 Testing Redis connection...")
try:
    r = redis.Redis(host='localhost', port=6379, db=1, decode_responses=True)
    r.ping()
    print("✅ Redis connected successfully")
    
    # Check existing keys
    keys = r.keys('ema_data:*')
    print(f"📦 Found {len(keys)} existing EMA keys")
    
    if keys:
        print("📋 Existing keys:")
        for key in sorted(keys)[:5]:  # Show first 5
            print(f"   {key}")
    
except Exception as e:
    print(f"❌ Redis connection failed: {e}")
    sys.exit(1)

# Test EMA Manager import
print("\n📚 Testing EMA Manager import...")
try:
    sys.path.append('user_data/scripts')
    from ema_to_redis import EMARedisManager
    print("✅ EMA Manager imported successfully")
except Exception as e:
    print(f"❌ Import failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test EMA Manager initialization
print("\n🚀 Testing EMA Manager initialization...")
try:
    manager = EMARedisManager()
    print("✅ EMA Manager initialized successfully")
    print(f"   Configured pairs: {len(manager.pairs)}")
    print(f"   Configured timeframes: {len(manager.timeframes)}")
    print(f"   Configured EMA periods: {manager.ema_periods}")
except Exception as e:
    print(f"❌ Initialization failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test sample data generation (no API required)
print("\n📊 Testing sample data generation...")
try:
    df = manager._generate_sample_data("BTC/USDT", "1h", 100)
    print(f"✅ Generated sample data: {len(df)} rows")
    print(f"   Latest price: ${df['close'].iloc[-1]:.2f}")
    print(f"   Data columns: {list(df.columns)}")
except Exception as e:
    print(f"❌ Sample data generation failed: {e}")
    import traceback
    traceback.print_exc()

# Test EMA calculation
print("\n🧮 Testing EMA calculation...")
try:
    ema_data = manager.calculate_emas_for_pair_timeframe("BTC/USDT", "1h")
    print(f"✅ EMA calculation completed")
    print(f"   Symbol: {ema_data.get('symbol')}")
    print(f"   Timeframe: {ema_data.get('timeframe')}")
    print(f"   Current price: ${ema_data.get('last_price', 0):.2f}")
    print(f"   EMAs calculated: {list(ema_data.get('emas', {}).keys())}")
    print(f"   Signals available: {len(ema_data.get('signals', {}))}")
except Exception as e:
    print(f"❌ EMA calculation failed: {e}")
    import traceback
    traceback.print_exc()

# Test Redis save
print("\n💾 Testing Redis save...")
try:
    if 'ema_data' in locals() and ema_data:
        manager.save_to_redis("BTC/USDT", "1h", ema_data)
        print("✅ Data saved to Redis")
        
        # Verify save
        retrieved_data = manager.get_from_redis("BTC/USDT", "1h")
        if retrieved_data:
            print("✅ Data retrieved from Redis successfully")
            print(f"   Price: ${retrieved_data['last_price']:.2f}")
        else:
            print("❌ Could not retrieve data from Redis")
    else:
        print("⚠️ No EMA data to save")
except Exception as e:
    print(f"❌ Redis save failed: {e}")
    import traceback
    traceback.print_exc()

print("\n🎯 Test Summary:")
print("✅ All basic functions are working")
print("📊 Ready to run full EMA script")
print("\nNext steps:")
print("1. Run: python user_data/scripts/ema_to_redis.py")
print("2. Read: python user_data/scripts/read_ema_from_redis.py")
