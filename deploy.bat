@echo off
REM Deployment script for agent-marketplace (Windows)

echo === Agent Marketplace Deployment ===

REM Check Python version
python --version
if %errorlevel% neq 0 (
    echo ERROR: Python not found
    exit /b 1
)

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies
    exit /b 1
)

REM Check for .env file
if not exist .env (
    echo WARNING: .env file not found. Creating from template...
    copy .env.example .env
    echo WARNING: Please edit .env with your configuration before running
    exit /b 1
)

REM Check for GCP credentials
if "%GOOGLE_APPLICATION_CREDENTIALS%"=="" (
    echo WARNING: GOOGLE_APPLICATION_CREDENTIALS not set
    echo Set it with: set GOOGLE_APPLICATION_CREDENTIALS=C:\path\to\key.json
    exit /b 1
)

if not exist "%GOOGLE_APPLICATION_CREDENTIALS%" (
    echo WARNING: GCP credentials file not found: %GOOGLE_APPLICATION_CREDENTIALS%
    exit /b 1
)

echo OK: GCP credentials found

REM Check if database exists
if exist marketplace.db (
    echo OK: Database exists
) else (
    echo OK: Database will be created on first run
)

REM Check MCP server
echo Checking MCP server...
curl -s http://localhost:8000/health >nul 2>&1
if %errorlevel% equ 0 (
    echo OK: MCP server is running (port 8000)
) else (
    echo WARNING: MCP server not detected on port 8000
    echo   Start it with: cd mcp-server ^&^& python server.py
)

REM Check A2A server
echo Checking A2A server...
curl -s http://localhost:9000/agents >nul 2>&1
if %errorlevel% equ 0 (
    echo OK: A2A server is running (port 9000)
) else (
    echo WARNING: A2A server not detected on port 9000
    echo   Start it with: cd a2a-server ^&^& python server.py
)

echo.
echo === Deployment Complete ===
echo Run: python app.py
echo Access UI: http://localhost:8500
