# 🚀 Houssam's Personal Trading Bot Ecosystem

Welcome to my personal cryptocurrency trading bot ecosystem! This consists of two main repositories that work together to provide a complete trading solution.

## 📊 Repository Overview

### 🤖 [Freqtrade Bot](https://github.com/houssamboudiar/freqtrade) ← You are here
**My personalized trading bot with custom EMA scripts and strategies**

- ⚡ Custom EMA calculation engine with Redis integration
- 📈 Personalized trading strategies and configurations
- 🔧 Custom scripts for market analysis and debugging
- 📊 Advanced backtesting and optimization tools

### 🎨 [FreqUI Dashboard](https://github.com/houssamboudiar/frequi)
**My personalized web interface for monitoring and controlling the trading bot**

- 🎨 Custom themes and personalized dashboard layouts
- 📊 Enhanced EMA visualization charts
- ⚡ Real-time trading data and performance metrics
- 📱 Responsive design for desktop and mobile

## 🚀 Quick Setup for Complete Ecosystem

### 1. Setup This Bot (Freqtrade)
```bash
# You're already here! Run the setup:
./setup_personal.sh  # Linux/Mac
# OR
setup_personal.bat   # Windows
```

### 2. Setup the UI Dashboard
```bash
# Clone and setup the UI
git clone https://github.com/houssamboudiar/frequi.git
cd frequi
./setup_personal.sh  # Linux/Mac or setup_personal.bat for Windows
```

### 3. Start Everything
1. Start Redis: `redis-server --daemonize yes`
2. Start this bot: `freqtrade trade --config user_data/config.json`
3. Start UI: `cd ../frequi && pnpm run dev`
4. Access dashboard: http://localhost:3000

## 🔗 Related Repository
- 🎨 **FreqUI Dashboard**: https://github.com/houssamboudiar/frequi

---
*Part of Houssam's personal trading bot ecosystem*
