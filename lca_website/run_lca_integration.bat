@echo off
echo ====================================
echo LCA集成系统启动脚本
echo ====================================

echo.
echo 步骤1: 激活Conda环境...
call conda activate olca_py311
if errorlevel 1 (
    echo 错误: 无法激活olca_py311环境
    echo 请确保已正确安装Conda环境
    pause
    exit /b 1
)

echo.
echo 步骤2: 检查openLCA连接...
echo 请确保：
echo - openLCA软件正在运行
echo - IPC服务器已启用（开发者工具 → IPC服务器）
echo - IPC服务器端口设置为8080
echo.
set /p continue="确认openLCA已准备就绪？(y/n): "
if /i not "%continue%"=="y" (
    echo 取消启动
    pause
    exit /b 0
)

echo.
echo 步骤3: 运行数据库迁移...
python migrate_lca_integration.py
if errorlevel 1 (
    echo 错误: 数据库迁移失败
    pause
    exit /b 1
)

echo.
echo 步骤4: 启动LCA集成网站...
echo 网站将在 http://localhost:8081 启动
echo 按 Ctrl+C 可停止服务器
echo.
python app.py

pause
