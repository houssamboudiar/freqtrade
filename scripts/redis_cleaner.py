#!/usr/bin/env python3
"""
Simple Redis Cleaner Script
Scans and deletes all data from Redis database
"""

import asyncio
import redis.asyncio as aioredis
import sys

async def connect_to_redis():
    """Connect to Redis database."""
    try:
        redis_client = aioredis.Redis(
            host='localhost',
            port=6379,
            db=0,
            decode_responses=True
        )
        await redis_client.ping()
        print("✅ Connected to Redis successfully!")
        return redis_client
    except Exception as e:
        print(f"❌ Failed to connect to Redis: {e}")
        return None

async def scan_redis_keys(redis_client):
    """Scan and count all keys in Redis."""
    try:
        keys = await redis_client.keys('*')
        print(f"📊 Found {len(keys)} total keys in Redis")
        
        # Show crypto-related keys count
        crypto_keys = await redis_client.keys('crypto:*')
        print(f"💰 Found {len(crypto_keys)} crypto-related keys")
        
        if len(keys) > 0:
            print("\n📋 Sample keys:")
            for i, key in enumerate(keys[:10]):  # Show first 10 keys
                print(f"  {i+1}. {key}")
            if len(keys) > 10:
                print(f"  ... and {len(keys) - 10} more keys")
        
        return keys
    except Exception as e:
        print(f"❌ Error scanning keys: {e}")
        return []

async def delete_all_data(redis_client):
    """Delete all data from Redis."""
    try:
        # Method 1: Use FLUSHDB command (fastest)
        print("\n🗑️  Deleting all data from Redis...")
        await redis_client.flushdb()
        print("✅ All data deleted successfully!")
        return True
    except Exception as e:
        print(f"❌ Error deleting data: {e}")
        return False

async def delete_crypto_data_only(redis_client):
    """Delete only crypto-related data."""
    try:
        crypto_keys = await redis_client.keys('crypto:*')
        if not crypto_keys:
            print("ℹ️  No crypto data found to delete")
            return True
        
        print(f"\n🗑️  Deleting {len(crypto_keys)} crypto keys...")
        
        # Delete in batches to avoid overwhelming Redis
        batch_size = 1000
        deleted_count = 0
        
        for i in range(0, len(crypto_keys), batch_size):
            batch = crypto_keys[i:i + batch_size]
            deleted = await redis_client.delete(*batch)
            deleted_count += deleted
            print(f"  Deleted batch {i//batch_size + 1}: {deleted} keys")
        
        print(f"✅ Deleted {deleted_count} crypto keys successfully!")
        return True
    except Exception as e:
        print(f"❌ Error deleting crypto data: {e}")
        return False

async def main():
    """Main function."""
    print("🧹 Redis Data Cleaner")
    print("=" * 30)
    
    # Connect to Redis
    redis_client = await connect_to_redis()
    if not redis_client:
        print("❌ Cannot proceed without Redis connection")
        return
    
    try:
        # Scan current data
        keys = await scan_redis_keys(redis_client)
        
        if not keys:
            print("ℹ️  Redis database is already empty")
            return
        
        # Ask user what to do
        print("\n🔧 Choose action:")
        print("1. Delete ALL data (FLUSHDB)")
        print("2. Delete only crypto data (crypto:*)")
        print("3. Cancel and exit")
        
        choice = input("\nEnter choice (1/2/3): ").strip()
        
        if choice == '1':
            print("\n⚠️  WARNING: This will delete ALL data in Redis!")
            confirm = input("Type 'YES' to confirm: ").strip()
            if confirm == 'YES':
                await delete_all_data(redis_client)
            else:
                print("❌ Operation cancelled")
                
        elif choice == '2':
            print("\n⚠️  This will delete all crypto-related data")
            confirm = input("Type 'yes' to confirm: ").strip()
            if confirm.lower() == 'yes':
                await delete_crypto_data_only(redis_client)
            else:
                print("❌ Operation cancelled")
                
        elif choice == '3':
            print("👋 Exiting without changes")
            
        else:
            print("❌ Invalid choice")
        
        # Show final count
        print("\n📊 Final scan:")
        await scan_redis_keys(redis_client)
        
    except KeyboardInterrupt:
        print("\n👋 Operation cancelled by user")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        # Close Redis connection
        if redis_client:
            await redis_client.aclose()
            print("🔌 Disconnected from Redis")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)