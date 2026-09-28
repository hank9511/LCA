Write-Host "Starting LCA service website..." -ForegroundColor Green
Write-Host ""

Write-Host "Installing dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt
Write-Host ""

Write-Host "Starting application..." -ForegroundColor Yellow
python app.py
Write-Host ""

Read-Host "Press any key to continue..."