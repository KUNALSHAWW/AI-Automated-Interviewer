@echo off
echo ========================================
echo   NavAI Real-Time - Backend Setup
echo ========================================
echo.

cd /d "%~dp0backend"

REM Check if venv exists
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Installing dependencies...
pip install -r requirements.txt

REM Check for .env file
if not exist ".env" (
    echo.
    echo WARNING: .env file not found!
    echo Copying .env.template to .env...
    copy .env.template .env
    echo.
    echo Please edit backend\.env and add your API keys:
    echo   - GROQ_API_KEY (required)
    echo   - DEEPGRAM_API_KEY (required)
    echo.
    pause
)

echo.
echo ========================================
echo   Starting Backend Server
echo ========================================
echo.
echo Server will start at: http://localhost:8000
echo WebSocket endpoint: ws://localhost:8000/ws/interview
echo.

python server.py

pause
