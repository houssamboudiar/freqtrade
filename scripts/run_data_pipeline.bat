@echo off
setlocal enabledelayedexpansion

:: Set window title
title Binance Data Pipeline - Historical + Real-time

:: Set colors for better visibility
color 0A

echo ================================================
echo    BINANCE DATA COLLECTION PIPELINE
echo ================================================
echo.
echo This script will:
echo 1. Download 6 months of historical data using Binance Data Collector
echo 2. Start real-time data collection using WebSocket Updater
echo.
echo Starting in 3 seconds...
timeout /t 3 /nobreak >nul

:: Change to the scripts directory
cd /d "c:\Users\houss\freqtrade\scripts"

echo.
echo ================================================
echo STEP 1: DOWNLOADING HISTORICAL DATA
echo ================================================
echo Starting Binance Data Collector...
echo.

:: Run the binance data collector and wait for completion
python binance_data_collector.py

:: Check if the previous command was successful
if %errorlevel% neq 0 (
    echo.
    echo ❌ ERROR: Binance Data Collector failed with error code %errorlevel%
    echo.
    echo Please check:
    echo - Internet connection
    echo - Redis server is running
    echo - Python dependencies are installed
    echo.
    pause
    exit /b %errorlevel%
)

echo.
echo ✅ Historical data collection completed successfully!
echo.
echo ================================================
echo STEP 2: STARTING REAL-TIME DATA COLLECTION
echo ================================================
echo Starting WebSocket Updater...
echo Press Ctrl+C to stop the real-time data collection
echo.

:: Small delay to let user read the message
timeout /t 2 /nobreak >nul

:: Run the websocket updater
python websocket_updater.py

:: If websocket updater exits, show status
if %errorlevel% neq 0 (
    echo.
    echo ⚠️  WebSocket Updater exited with error code %errorlevel%
) else (
    echo.
    echo ✅ WebSocket Updater completed successfully!
)

echo.
echo ================================================
echo DATA PIPELINE FINISHED
echo ================================================
echo.
pause
