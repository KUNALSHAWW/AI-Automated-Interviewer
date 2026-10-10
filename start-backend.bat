@echo off
echo ========================================
echo   NavAI Viva - backend
echo ========================================
cd /d "%~dp0backend"

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)
call .venv\Scripts\activate.bat

echo Installing dependencies...
pip install -q -r requirements.txt

if not exist ".env" (
    copy .env.example .env >nul
    echo.
    echo Created backend\.env from .env.example. Add at least one chat key and one speech-to-text key, then run again.
    echo   OLLAMA_API_KEY   chat + vision   ^(ollama.com/settings/keys^)
    echo   GROQ_API_KEY     fast chat + Whisper speech-to-text
    pause
    exit /b 1
)

echo.
echo Checking providers ^(optional: python scripts\provider_check.py^)
echo Server: http://127.0.0.1:8000
python server.py
pause
