@echo off
cd /d "%~dp0"
echo Testing LCA Website...
echo.
echo Current directory: %CD%
echo.
echo Checking files...
if exist app.py (
    echo ✓ Found app.py
) else (
    echo ❌ app.py not found
    pause
    exit /b 1
)
echo.
echo Installing dependencies...
pip install flask flask-sqlalchemy flask-login werkzeug pandas openpyxl openai
echo.
echo Starting website on port 8080...
echo Local access: http://localhost:8080
echo WLAN access: http://172.18.45.109:8080
echo.
echo Press Ctrl+C to stop
python app.py
pause