# Project Structure - Houssam's Personal Freqtrade

This document outlines the structure and purpose of files in this personalized Freqtrade repository.

## 📁 Core Directory Structure

```
freqtrade/
├── 📄 README.md                    # Personal repository overview
├── 📄 setup_personal.bat          # Windows setup script
├── 📄 setup_personal.sh           # Linux/Mac setup script
├── 📄 .gitignore                  # Git ignore rules (personalized)
├── 📁 freqtrade/                  # Core trading bot engine
├── 📁 user_data/                  # Personal trading data & configs
│   ├── 📁 scripts/                # 🌟 My custom scripts
│   │   ├── 📄 ema_to_redis.py     # EMA calculation with Redis
│   │   ├── 📄 read_ema_from_redis.py # Redis data retrieval
│   │   ├── 📄 debug_ema.py        # EMA debugging tools
│   │   ├── 📄 test_ema.py         # EMA testing utilities
│   │   ├── 📄 test_ema_quick.py   # Quick EMA tests
│   │   ├── 📄 requirements.txt    # Script dependencies
│   │   └── 📄 README.md           # Scripts documentation
│   ├── 📁 strategies/             # Trading strategies
│   ├── 📁 hyperopts/              # Hyperoptimization configs
│   └── 📄 config.json             # Main bot configuration
├── 📁 docs/                       # Documentation
└── 📁 tests/                      # Test files
```

## 🌟 Custom Scripts Overview

### `ema_to_redis.py`
- **Purpose**: Calculates EMA values and stores them in Redis
- **Features**: Real-time EMA calculation, Redis integration
- **Usage**: `python user_data/scripts/ema_to_redis.py`

### `read_ema_from_redis.py`
- **Purpose**: Retrieves and displays EMA data from Redis
- **Features**: Data visualization, historical EMA analysis
- **Usage**: `python user_data/scripts/read_ema_from_redis.py`

### `debug_ema.py`
- **Purpose**: Debug and analyze EMA calculations
- **Features**: EMA accuracy testing, performance analysis
- **Usage**: `python user_data/scripts/debug_ema.py`

### `test_ema.py` & `test_ema_quick.py`
- **Purpose**: Unit tests for EMA functionality
- **Features**: Automated testing, validation
- **Usage**: `python user_data/scripts/test_ema.py`

## 🚀 Quick Start Commands

1. **Setup**: `./setup_personal.sh` (Linux/Mac) or `setup_personal.bat` (Windows)
2. **Run EMA Script**: `python user_data/scripts/ema_to_redis.py`
3. **Start Trading**: `freqtrade trade --config user_data/config.json`
4. **Backtest**: `freqtrade backtesting --config user_data/config.json`

## 🔧 Configuration Files

- `user_data/config.json` - Main trading configuration
- `user_data/scripts/requirements.txt` - Python dependencies for custom scripts
- `.gitignore` - Excludes sensitive data and temporary files

## 📊 Data Management

The repository is configured to:
- ✅ **Include**: Custom scripts, strategies, documentation
- ❌ **Exclude**: Trading logs, backtest results, sensitive config data
- 🔄 **Redis**: Used for real-time EMA data storage and retrieval

---

*This is a personal fork of [Freqtrade](https://github.com/freqtrade/freqtrade) customized by Houssam Boudiar.*
