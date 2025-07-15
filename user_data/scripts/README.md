# EMA Data to Redis Scripts

This directory contains Python scripts to calculate EMA (Exponential Moving Average) indicators and store them in Redis for fast access.

## Files

- `ema_to_redis.py` - Main script that calculates EMAs and saves to Redis
- `read_ema_from_redis.py` - Helper script to read and display EMA data from Redis
- `requirements.txt` - Python dependencies
- `README.md` - This file

## Setup

### 1. Install Python Dependencies

```bash
# Install the required Python packages
pip install -r requirements.txt
```

### 2. Environment Variables

Make sure your `.env` file in the `user_data` directory contains your Binance API credentials:

```env
BINANCE_API_KEY=your_api_key_here
BINANCE_SECRET_KEY=your_secret_key_here
```

### 3. Make sure Redis is running

```bash
# Check if Redis is running
docker-compose ps

# If not running, start it
docker-compose up -d redis
```

## Usage

### Calculate and Store EMA Data

```bash
# Navigate to the scripts directory
cd user_data/scripts

# Run the main EMA calculation script
python ema_to_redis.py
```

This script will:
- Fetch OHLCV data for BTC/USDT, ETH/USDT, and USUAL/USDT
- Calculate EMAs for periods: 9, 21, 50, 100, 200
- Generate trading signals based on EMA relationships
- Store all data in Redis with 1-hour expiry

### Read EMA Data from Redis

```bash
# View all available EMA data
python read_ema_from_redis.py

# View data for a specific symbol
python read_ema_from_redis.py BTC/USDT
```

### Manual Redis Access

You can also access the data directly using Redis CLI:

```bash
# Connect to Redis
docker exec -it freqtrade_redis redis-cli

# Switch to database 1 (where EMA data is stored)
redis> SELECT 1

# List all EMA keys
redis> KEYS ema_data:*

# Get specific EMA data
redis> GET ema_data:BTC_USDT

# Get just the EMA-9 value for BTC
redis> GET ema_data:BTC_USDT:ema_9

# Get trading signals
redis> GET ema_data:BTC_USDT:signals
```

## Data Structure

The EMA data is stored in Redis with the following structure:

```json
{
  "symbol": "BTC/USDT",
  "timestamp": "2025-07-14T18:30:00.123456",
  "last_price": 65432.10,
  "emas": {
    "ema_9": {
      "value": 65500.25,
      "previous": 65480.15,
      "trend": "up"
    },
    "ema_21": {
      "value": 65200.50,
      "previous": 65150.30,
      "trend": "up"
    }
    // ... more EMA periods
  },
  "signals": {
    "price_above_ema9": true,
    "price_above_ema21": true,
    "price_above_ema50": true,
    "ema9_above_ema21": true,
    "ema21_above_ema50": true,
    "bullish_alignment": true,
    "bearish_alignment": false
  }
}
```

## Redis Keys

- `ema_data:{SYMBOL}` - Complete EMA data for a symbol
- `ema_data:{SYMBOL}:ema_{PERIOD}` - Individual EMA value
- `ema_data:{SYMBOL}:signals` - Trading signals
- `ema_data:{SYMBOL}:last_update` - Last update timestamp

## Configuration

You can modify the following variables in `ema_to_redis.py`:

- `self.ema_periods` - EMA periods to calculate
- `self.pairs` - Trading pairs to process
- `self.timeframe` - Timeframe for data (5m, 15m, 1h, etc.)
- `redis_db` - Redis database number (default: 1)

## Automation

To run this script automatically, you can:

1. **Cron job** (Linux/Mac):
```bash
# Run every 5 minutes
*/5 * * * * cd /path/to/freqtrade/user_data/scripts && python ema_to_redis.py
```

2. **Task Scheduler** (Windows):
Create a task to run `python ema_to_redis.py` every 5 minutes

3. **Docker container** (Advanced):
Create a separate container that runs this script periodically

## Troubleshooting

### Redis Connection Issues
- Make sure Redis container is running: `docker-compose ps`
- Check Redis logs: `docker-compose logs redis`

### Exchange API Issues
- Verify your API keys are correct
- Check API key permissions on Binance
- If no API keys, the script will generate sample data for testing

### Import Errors
- Make sure all dependencies are installed: `pip install -r requirements.txt`
- Consider using a virtual environment

## Integration with Freqtrade

You can use this EMA data in your freqtrade strategies by connecting to Redis:

```python
import redis
import json

class MyStrategy(IStrategy):
    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.redis_client = redis.Redis(host='redis', port=6379, db=1, decode_responses=True)
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Get EMA data from Redis
        symbol = metadata['pair'].replace('/', '_')
        ema_data = self.redis_client.get(f"ema_data:{symbol}")
        
        if ema_data:
            data = json.loads(ema_data)
            # Use the EMA data in your strategy
            self.dp.get_pair_dataframe(metadata['pair'], '5m')
        
        return dataframe
```
