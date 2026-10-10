@echo off
echo ========================================
echo   NavAI Viva - frontend (dev server)
echo ========================================
cd /d "%~dp0frontend"
if not exist "node_modules" (
    echo Installing dependencies...
    call npm install
)
echo Open http://localhost:3000  ^(the API must be running on port 8000^)
call npm run dev
pause
