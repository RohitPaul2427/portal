@echo off
echo Stopping LEAMSS services...
taskkill /F /IM mongod.exe 2>nul
taskkill /F /IM uvicorn.exe 2>nul
taskkill /F /IM node.exe 2>nul
echo All services stopped.
