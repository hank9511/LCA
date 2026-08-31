Write-Host "Starting LCA Website..." -ForegroundColor Green
Write-Host ""

Write-Host "Step 1: Installing Python dependencies..." -ForegroundColor Yellow
pip install flask flask-sqlalchemy flask-login werkzeug
Write-Host ""

Write-Host "Step 2: Starting the website..." -ForegroundColor Yellow
python app.py
Write-Host ""

Read-Host "Press any key to continue..."