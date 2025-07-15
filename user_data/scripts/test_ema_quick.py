#!/usr/bin/env python3
"""
Quick EMA Test Script
Test the EMA functionality with just one pair and timeframe
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ema_to_redis import EMARedisManager

def test_ema():
    print("🧪 Testing EMA Redis Manager...")
    
    try:
        # Initialize manager
        manager = EMARedisManager()
        print("✅ EMA Manager initialized")
        
        # Test with just one pair and timeframe
        test_pairs = ["BTC/USDT"]
        test_timeframes = ["1h"]
        
        print(f"🔄 Testing with {test_pairs[0]} on {test_timeframes[0]} timeframe...")
        
        # Update just this one combination
        manager.update_all_pairs(
            selected_pairs=test_pairs,
            selected_timeframes=test_timeframes
        )
        
        print("✅ Test completed successfully!")
        
        # Try to read the data back
        data = manager.get_from_redis("BTC/USDT", "1h")
        if data:
            print(f"✅ Successfully read data from Redis")
            print(f"   Price: ${data['last_price']:.2f}")
            print(f"   EMAs calculated: {list(data['emas'].keys())}")
        else:
            print("❌ No data found in Redis")
            
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_ema()
