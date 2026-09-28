@echo off
echo ====================================
echo LCA Integration System Startup Script
echo ====================================

echo.
echo Step 1: Activating Conda environment...
call conda activate olca_py311
if errorlevel 1 (
    echo Error: Failed to activate olca_py311 environment
    echo Please ensure the Conda environment is installed correctly
    pause
    exit /b 1
)

echo.
echo Step 2: Checking openLCA connection...
echo Please ensure:
echo - openLCA software is running
echo - IPC server is enabled (Developer Tools → IPC Server)
echo - IPC server port is set to 8080
echo.
set /p continue="Confirm openLCA is ready? (y/n): "
if /i not "%continue%"=="y" (
    echo Startup cancelled
    pause
    exit /b 0
)

echo.
echo Step 3: Running database migration...
python migrate_lca_integration.py
if errorlevel 1 (
    echo Error: Database migration failed
    pause
    exit /b 1
)

echo.
echo Step 4: Starting LCA integration website...
echo Website will start at http://localhost:8081
echo Press Ctrl+C to stop the server
echo.
python app.py

pause
