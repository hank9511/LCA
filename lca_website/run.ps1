Write-Host "启动LCA服务网站..." -ForegroundColor Green
Write-Host ""

Write-Host "正在安装依赖..." -ForegroundColor Yellow
pip install -r requirements.txt
Write-Host ""

Write-Host "启动应用..." -ForegroundColor Yellow
python app.py
Write-Host ""

Read-Host "按任意键继续..."