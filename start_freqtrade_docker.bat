@echo off
echo Stopping existing FreqTrade containers...
docker stop freqtrade 2>nul
docker rm freqtrade 2>nul

echo Starting FreqTrade with demo configuration...
docker run -d --name freqtrade -v "%~dp0user_data:/freqtrade/user_data" -p 8080:8080 freqtrade:local trade --config /freqtrade/user_data/config_demo.json --strategy DemoStrategy

echo FreqTrade is running! You can access the UI at http://localhost:8080
echo Use the following credentials:
echo Username: freqtrade
echo Password: password
