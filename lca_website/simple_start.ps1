# 获取脚本所在目录
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Write-Host "Script directory: $scriptDir" -ForegroundColor Green

# 切换到脚本目录
Set-Location $scriptDir
Write-Host "Current working directory: $PWD" -ForegroundColor Green

# 检查app.py是否存在
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