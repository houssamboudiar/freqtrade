@echo off
REM EMA to Redis Runner Script
REM This batch file makes it easy to run the EMA calculation script

echo.
echo ============================================
echo           EMA to Redis Script
echo ============================================
echo.

REM Change to the scripts directory
cd /d "c:\Users\houss\freqtrade\user_data\scripts"

REM Run the EMA calculation script
echo Running EMA calculation script...
"C:\Users\houss\freqtrade\.env\Scripts\python.exe" ema_to_redis.py

echo.
echo ============================================
echo          Script completed!
echo ============================================
echo.

pause
