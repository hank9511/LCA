@echo off
echo Starting LCA Website...
echo.
echo Step 1: Installing Python dependencies...
pip install flask flask-sqlalchemy flask-login werkzeug
echo.
echo Step 2: Starting the website...
python app.py
echo.
pause