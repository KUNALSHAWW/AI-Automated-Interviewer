@echo off
echo ========================================
echo   NavAI Real-Time - Frontend Setup
echo ========================================
echo.

cd /d "%~dp0frontend"

REM Check if node_modules exists
if not exist "node_modules" (
    echo Installing dependencies...
    npm install
)

echo.
echo ========================================
echo   Starting Frontend Dev Server
echo ========================================
echo.
echo Frontend will start at: http://localhost:3000
echo Make sure the backend is running first!
echo.

npm run dev

pause
