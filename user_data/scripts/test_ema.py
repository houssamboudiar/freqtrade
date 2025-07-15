#!/usr/bin/env python3
"""
Quick EMA Test Script
====================

Test the new multi-timeframe EMA script with a few pairs and timeframes.
"""

import sys
import os

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ema_to_redis import EMARedisManager

def main():
    print("🧪 Testing Multi-Timeframe EMA Script")
    print("=" * 50)
    
    # Initialize the manager
    manager = EMARedisManager()
    
    # Configure for testing with fewer pairs and timeframes
    test_pairs = ["BTC/USDT", "ETH/USDT", "USUAL/USDT"]
    test_timeframes = ["1h", "4h", "1d"]
    
    manager.configure_pairs(test_pairs)
    manager.configure_timeframes(test_timeframes)
    
    print(f"Testing with {len(test_pairs)} pairs and {len(test_timeframes)} timeframes...")
    
    # Update the test data
    manager.update_all_pairs()
    
    # Show market overview
    manager.print_market_overview()
    
    print("\n✅ Test completed!")

if __name__ == "__main__":
    main()
