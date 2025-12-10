@echo off
echo ---------------------------------------------------
echo      SODIUM TYCOON - RAPID RESTART SYSTEM
echo ---------------------------------------------------

echo [1/4] 🛑 Closing old Terminal Windows...
:: Forcefully close the specific windows by their Title
taskkill /F /FI "WINDOWTITLE eq SodiumTycoon BOT" >nul 2>&1
taskkill /F /FI "WINDOWTITLE eq SodiumTycoon DASHBOARD" >nul 2>&1

echo [2/4] 🧹 Cleaning up lingering Python processes...
:: Nuke any leftover python scripts (just in case)
taskkill /F /IM python.exe >nul 2>&1

echo [3/4] 🤖 Starting SodiumTycoon BOT...
:: Launch new window with specific Title
start "SodiumTycoon BOT" cmd /k "cd applications\bot && poetry run python main.py"

echo [4/4] 🌐 Starting SodiumTycoon DASHBOARD...
:: Launch new window with specific Title
start "SodiumTycoon DASHBOARD" cmd /k "cd applications\web && poetry run flask --app src.app run"

echo.
echo ✅ Done! Old windows closed, new systems launching.
echo ---------------------------------------------------