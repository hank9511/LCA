@echo off
cd /d "%~dp0"
echo Starting LCA Website with External Access...
echo.
echo Installing dependencies...
pip install flask flask-sqlalchemy flask-login werkzeug pandas openpyxl openai
echo.
echo Starting website on port 8080...
echo Local access: http://localhost:8080
echo External access: http://[YOUR_IP]:8080
echo.
python app.py
pause