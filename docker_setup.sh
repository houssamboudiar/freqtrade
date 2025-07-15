#!/bin/bash
# Personal Freqtrade Docker Setup Script
# Author: Houssam Boudiar

echo "🐳 Setting up Houssam's Personal Freqtrade with Docker..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    echo "   Download from: https://www.docker.com/get-started"
    exit 1
fi

# Check if Docker Compose is available
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose is not available. Please install Docker Compose."
    exit 1
fi

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "⚙️  Creating environment file..."
    cp .env.example .env
    echo "✅ Environment file created!"
    echo "🔐 IMPORTANT: Please edit .env with your actual API keys before starting:"
    echo "   - BINANCE_API_KEY"
    echo "   - BINANCE_SECRET_KEY"
    echo ""
    read -p "Press Enter to continue after editing .env file..."
else
    echo "✅ Environment file already exists."
fi

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p user_data/logs
mkdir -p user_data/backtest_results
mkdir -p user_data/hyperopt_results

# Pull latest Docker images
echo "📦 Pulling latest Docker images..."
docker-compose pull

echo "🚀 Starting Freqtrade ecosystem..."

# Start services
docker-compose up -d

echo "✅ Docker containers started!"
echo ""
echo "📊 Services Status:"
docker-compose ps
echo ""
echo "📖 Next steps:"
echo "   1. Check logs: docker-compose logs -f freqtrade"
echo "   2. Access FreqUI: http://localhost:3000 (if you have FreqUI running)"
echo "   3. API available at: http://localhost:8080"
echo "   4. Stop services: docker-compose down"
echo ""
echo "🔧 Useful Docker commands:"
echo "   - View logs: docker-compose logs -f freqtrade"
echo "   - Restart bot: docker-compose restart freqtrade"
echo "   - Enter container: docker-compose exec freqtrade bash"
echo "   - Run EMA script: docker-compose exec freqtrade python user_data/scripts/ema_to_redis.py"
