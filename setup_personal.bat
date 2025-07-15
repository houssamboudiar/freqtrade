@echo off
REM Personal Freqtrade Setup Script for Windows
REM Author: Houssam Boudiar

echo 🚀 Setting up Houssam's Personal Freqtrade Repository...

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed. Please install Python 3.8+ first.
    pause
    exit /b 1
)

REM Install Python dependencies
echo 📦 Installing Python dependencies...
pip install -r requirements.txt

REM Install additional dependencies for custom scripts
echo 📦 Installing custom script dependencies...
cd user_data\scripts
pip install -r requirements.txt
cd ..\..

REM Create config from example if it doesn't exist
if not exist "user_data\config.json" (
    echo ⚙️ Creating configuration file...
    copy "config_examples\config_binance.example.json" "user_data\config.json"
    echo ✅ Config created! Please edit user_data\config.json with your API keys.
) else (
    echo ✅ Configuration already exists.
)

echo 🎉 Setup complete!
echo.
echo 📖 Next steps:
echo    1. Edit user_data\config.json with your exchange API keys
echo    2. Run: python user_data\scripts\ema_to_redis.py
echo    3. Run: freqtrade trade --config user_data\config.json
echo.
echo 🔧 Custom Scripts:
echo    - EMA to Redis: python user_data\scripts\ema_to_redis.py
echo    - Read EMA: python user_data\scripts\read_ema_from_redis.py
echo    - Debug EMA: python user_data\scripts\debug_ema.py
echo.
pause
