@echo off
REM Flush Redis database, run data collector, integrity checker, and websocket updater in sequence

REM Step 2: Run Binance Data Collector
ECHO Running Binance Data Collector...
python scripts\binance_data_collector.py
IF %ERRORLEVEL% NEQ 0 (
    ECHO Binance Data Collector failed.
    PAUSE
    EXIT /B 1
)

REM Step 3: Run Data Integrity Checker
ECHO Running Data Integrity Checker...
python scripts\data_integrity_checker.py
IF %ERRORLEVEL% NEQ 0 (
    ECHO Data Integrity Checker failed.
    PAUSE
    EXIT /B 1
)

REM Step 4: Run WebSocket Updater
ECHO Running WebSocket Updater...
python scripts\websocket_updater.py
IF %ERRORLEVEL% NEQ 0 (
    ECHO WebSocket Updater failed.
    PAUSE
    EXIT /B 1
)

ECHO All steps completed successfully.
PAUSE
