# Resolve the directory that contains this script
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "Script directory: $scriptDir" -ForegroundColor Green

# Change to the script directory
Set-Location $scriptDir
Write-Host "Current working directory: $PWD" -ForegroundColor Green

# Check that app.py exists
if (Test-Path "app.py") {
    Write-Host "✓ Found app.py" -ForegroundColor Green
} else {
    Write-Host "❌ app.py not found!" -ForegroundColor Red
    exit 1
}

Write-Host "Installing dependencies..." -ForegroundColor Yellow
pip install flask flask-sqlalchemy flask-login werkzeug

Write-Host "Starting LCA website..." -ForegroundColor Yellow
python app.py

Read-Host "Press any key to continue..."