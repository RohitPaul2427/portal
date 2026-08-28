@echo off
echo Starting LEAMSS Immigration Portal...

:: 1. Start MongoDB
echo [1/3] Starting MongoDB...
start "MongoDB" /min "%~dp0mongodb_bin\bin\mongod.exe" --dbpath "%~dp0data\db" --port 27017 --bind_ip 127.0.0.1

:: 2. Start Backend
echo [2/3] Starting Backend API...
start "Backend" /min cmd /c "cd /d %~dp0backend && venv\Scripts\uvicorn.exe server:app --host 0.0.0.0 --port 8001"

:: 3. Start Frontend
echo [3/3] Starting Frontend UI...
start "Frontend" /min cmd /c "cd /d %~dp0frontend && set BROWSER=none && npm.cmd start"

echo.
echo All services started!
echo Frontend: http://localhost:3000
echo Backend:  http://localhost:8001/docs
echo.
timeout /t 3 >nul
start http://localhost:3000
