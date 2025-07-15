@echo off
REM Freqtrade Docker Management Script for Windows
REM Author: Houssam Boudiar

if "%1"=="" goto usage

if "%1"=="start" goto start
if "%1"=="start-dev" goto start_dev
if "%1"=="start-prod" goto start_prod
if "%1"=="stop" goto stop
if "%1"=="restart" goto restart
if "%1"=="logs" goto logs
if "%1"=="status" goto status
if "%1"=="backtest" goto backtest
if "%1"=="shell" goto shell
if "%1"=="ema" goto ema
if "%1"=="update" goto update
if "%1"=="clean" goto clean
goto usage

:start
echo 🚀 Starting Freqtrade...
docker-compose up -d
goto end

:start_dev
echo 🔧 Starting in development mode...
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
goto end

:start_prod
echo 🏭 Starting in production mode...
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
goto end

:stop
echo ⏹️ Stopping services...
docker-compose down
goto end

:restart
echo 🔄 Restarting Freqtrade bot...
docker-compose restart freqtrade
goto end

:logs
echo 📋 Showing live logs...
docker-compose logs -f freqtrade
goto end

:status
echo 📊 Services status:
docker-compose ps
goto end

:backtest
echo 📈 Running backtest...
docker-compose exec freqtrade freqtrade backtesting --config /freqtrade/user_data/config.json --strategy SampleStrategy
goto end

:shell
echo 🐚 Entering Freqtrade container...
docker-compose exec freqtrade bash
goto end

:ema
echo 📊 Running EMA script...
docker-compose exec freqtrade python /freqtrade/user_data/scripts/ema_to_redis.py
goto end

:update
echo 📦 Updating Docker images...
docker-compose pull
goto end

:clean
echo 🧹 Cleaning up...
docker-compose down -v
docker system prune -f
goto end

:usage
echo 🐳 Houssam's Freqtrade Docker Manager
echo.
echo Usage: %0 [command]
echo.
echo Commands:
echo   start         Start Freqtrade in trading mode
echo   start-dev     Start in development mode
echo   start-prod    Start in production mode
echo   stop          Stop all services
echo   restart       Restart Freqtrade bot
echo   logs          Show live logs
echo   status        Show services status
echo   backtest      Run backtesting
echo   shell         Enter Freqtrade container
echo   ema           Run custom EMA script
echo   update        Update Docker images
echo   clean         Clean up containers and volumes
echo.
goto end

:end
