#!/bin/bash
# Personal Freqtrade Setup Script
# Author: Houssam Boudiar

echo "🚀 Setting up Houssam's Personal Freqtrade Repository..."

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8+ first."
    exit 1
fi

# Check if Redis is installed (for EMA scripts)
if ! command -v redis-server &> /dev/null; then
    echo "⚠️  Redis is not installed. Installing Redis for EMA scripts..."
    # Add Redis installation commands based on OS
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        sudo apt-get update
        sudo apt-get install redis-server -y
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        brew install redis
    else
        echo "⚠️  Please install Redis manually for your operating system"
    fi
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip3 install -r requirements.txt

# Install additional dependencies for custom scripts
echo "📦 Installing custom script dependencies..."
cd user_data/scripts
pip3 install -r requirements.txt
cd ../..

# Create config from example if it doesn't exist
if [ ! -f "user_data/config.json" ]; then
    echo "⚙️  Creating configuration file..."
    cp config_examples/config_binance.example.json user_data/config.json
    echo "✅ Config created! Please edit user_data/config.json with your API keys."
else
    echo "✅ Configuration already exists."
fi

# Start Redis server
echo "🔄 Starting Redis server..."
redis-server --daemonize yes

echo "🎉 Setup complete!"
echo ""
echo "📖 Next steps:"
echo "   1. Edit user_data/config.json with your exchange API keys"
echo "   2. Run: python3 user_data/scripts/ema_to_redis.py"
echo "   3. Run: freqtrade trade --config user_data/config.json"
echo ""
echo "🔧 Custom Scripts:"
echo "   - EMA to Redis: python3 user_data/scripts/ema_to_redis.py"
echo "   - Read EMA: python3 user_data/scripts/read_ema_from_redis.py"
echo "   - Debug EMA: python3 user_data/scripts/debug_ema.py"
