@echo off
chcp 65001 >nul
echo Starting LCA Service Website...
echo.
echo Installing dependencies...
pip install -r requirements.txt
echo.
echo Starting application...
python app.py
echo.
pause