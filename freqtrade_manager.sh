#!/bin/bash
# Freqtrade Docker Management Script
# Author: Houssam Boudiar

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_color() {
    printf "${1}${2}${NC}\n"
}

# Function to show usage
show_usage() {
    print_color $BLUE "🐳 Houssam's Freqtrade Docker Manager"
    echo ""
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  start         Start Freqtrade in trading mode"
    echo "  start-dev     Start in development mode"
    echo "  start-prod    Start in production mode"
    echo "  stop          Stop all services"
    echo "  restart       Restart Freqtrade bot"
    echo "  logs          Show live logs"
    echo "  status        Show services status"
    echo "  backtest      Run backtesting"
    echo "  shell         Enter Freqtrade container"
    echo "  ema           Run custom EMA script"
    echo "  update        Update Docker images"
    echo "  clean         Clean up containers and volumes"
    echo ""
}

# Main script logic
case "$1" in
    "start")
        print_color $GREEN "🚀 Starting Freqtrade..."
        docker-compose up -d
        ;;
    "start-dev")
        print_color $YELLOW "🔧 Starting in development mode..."
        docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
        ;;
    "start-prod")
        print_color $GREEN "🏭 Starting in production mode..."
        docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
        ;;
    "stop")
        print_color $RED "⏹️  Stopping services..."
        docker-compose down
        ;;
    "restart")
        print_color $YELLOW "🔄 Restarting Freqtrade bot..."
        docker-compose restart freqtrade
        ;;
    "logs")
        print_color $BLUE "📋 Showing live logs..."
        docker-compose logs -f freqtrade
        ;;
    "status")
        print_color $BLUE "📊 Services status:"
        docker-compose ps
        ;;
    "backtest")
        print_color $YELLOW "📈 Running backtest..."
        docker-compose exec freqtrade freqtrade backtesting --config /freqtrade/user_data/config.json --strategy SampleStrategy
        ;;
    "shell")
        print_color $BLUE "🐚 Entering Freqtrade container..."
        docker-compose exec freqtrade bash
        ;;
    "ema")
        print_color $GREEN "📊 Running EMA script..."
        docker-compose exec freqtrade python /freqtrade/user_data/scripts/ema_to_redis.py
        ;;
    "update")
        print_color $YELLOW "📦 Updating Docker images..."
        docker-compose pull
        ;;
    "clean")
        print_color $RED "🧹 Cleaning up..."
        docker-compose down -v
        docker system prune -f
        ;;
    *)
        show_usage
        ;;
esac
