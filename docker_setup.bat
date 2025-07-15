@echo off
REM Personal Freqtrade Docker Setup Script for Windows
REM Author: Houssam Boudiar

echo 🐳 Setting up Houssam's Personal Freqtrade with Docker...

REM Check if Docker is installed
docker --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker is not installed. Please install Docker Desktop first.
    echo    Download from: https://www.docker.com/get-started
    pause
    exit /b 1
)

REM Create .env file if it doesn't exist
if not exist ".env" (
    echo ⚙️ Creating environment file...
    copy ".env.example" ".env"
    echo ✅ Environment file created!
    echo 🔐 IMPORTANT: Please edit .env with your actual API keys before starting:
    echo    - BINANCE_API_KEY
    echo    - BINANCE_SECRET_KEY
    echo.
    pause
) else (
    echo ✅ Environment file already exists.
)

REM Create necessary directories
echo 📁 Creating necessary directories...
if not exist "user_data\logs" mkdir "user_data\logs"
if not exist "user_data\backtest_results" mkdir "user_data\backtest_results"
if not exist "user_data\hyperopt_results" mkdir "user_data\hyperopt_results"

REM Pull latest Docker images
echo 📦 Pulling latest Docker images...
docker-compose pull

echo 🚀 Starting Freqtrade ecosystem...

REM Start services
docker-compose up -d

echo ✅ Docker containers started!
echo.
echo 📊 Services Status:
docker-compose ps
echo.
echo 📖 Next steps:
echo    1. Check logs: docker-compose logs -f freqtrade
echo    2. Access FreqUI: http://localhost:3000 (if you have FreqUI running)
echo    3. API available at: http://localhost:8080
echo    4. Stop services: docker-compose down
echo.
echo 🔧 Useful Docker commands:
echo    - View logs: docker-compose logs -f freqtrade
echo    - Restart bot: docker-compose restart freqtrade
echo    - Enter container: docker-compose exec freqtrade bash
echo    - Run EMA script: docker-compose exec freqtrade python user_data/scripts/ema_to_redis.py
echo.
pause
