@echo off
REM ============================================================================
REM Agent Marketplace — Full Stack Startup
REM ============================================================================
REM Launches all services in the correct order:
REM   1. MCP Server (tools)
REM   2. A2A Server (agents)
REM   3. Marketplace (governance)
REM   4. Demo agents (optional)
REM
REM CONFIGURE PATHS BELOW before first run.
REM ============================================================================

REM ---------------------------------------------------------------------------
REM CONFIGURATION — Edit these paths for your environment
REM ---------------------------------------------------------------------------
set MCP_SERVER_DIR=C:\work\my-github-repos\rsagenticai-mcp-server
set MCP_SERVER_CMD=python run_server.py
set MCP_SERVER_PORT=9595

set A2A_SERVER_DIR=C:\work\projects\ap2_a2a_server
set A2A_SERVER_CMD=python main.py
set A2A_SERVER_PORT=9000

set MARKETPLACE_DIR=C:\work\agent-marketplace
set MARKETPLACE_CMD=python app.py
set MARKETPLACE_PORT=8500

set DEMO_CREDIT_DIR=%MARKETPLACE_DIR%\demo_agents\credit-decision-agent
set DEMO_KYC_DIR=%MARKETPLACE_DIR%\demo_agents\kyc-verification-agent

REM Set to 1 to start demo agents, 0 to skip
REM Demo agents are for showcasing governance — not needed for normal use
set START_DEMO_AGENTS=1

REM ---------------------------------------------------------------------------
REM PRE-FLIGHT CHECKS
REM ---------------------------------------------------------------------------
echo ============================================================================
echo  Agent Marketplace — Startup
echo ============================================================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [FAIL] Python not found on PATH
    exit /b 1
)

if not exist "%MARKETPLACE_DIR%\.env" (
    echo [WARN] .env not found — copying from .env.example
    if exist "%MARKETPLACE_DIR%\.env.example" (
        copy "%MARKETPLACE_DIR%\.env.example" "%MARKETPLACE_DIR%\.env" >nul
        echo [WARN] Edit %MARKETPLACE_DIR%\.env with your GCP credentials before governance reviews will work
    ) else (
        echo [WARN] No .env.example found either — governance reviews will be disabled
    )
)

REM ---------------------------------------------------------------------------
REM 1. MCP SERVER
REM ---------------------------------------------------------------------------
echo [1/4] Starting MCP Server on port %MCP_SERVER_PORT%...
if exist "%MCP_SERVER_DIR%" (
    start "MCP Server (port %MCP_SERVER_PORT%)" cmd /k "cd /d %MCP_SERVER_DIR% && %MCP_SERVER_CMD%"
    timeout /t 3 /nobreak >nul
) else (
    echo [SKIP] MCP Server directory not found: %MCP_SERVER_DIR%
    echo        Marketplace will run without tool discovery.
)

REM ---------------------------------------------------------------------------
REM 2. A2A SERVER
REM ---------------------------------------------------------------------------
echo [2/4] Starting A2A Server on port %A2A_SERVER_PORT%...
if exist "%A2A_SERVER_DIR%" (
    start "A2A Server (port %A2A_SERVER_PORT%)" cmd /k "cd /d %A2A_SERVER_DIR% && %A2A_SERVER_CMD%"
    timeout /t 3 /nobreak >nul
) else (
    echo [SKIP] A2A Server directory not found: %A2A_SERVER_DIR%
    echo        Marketplace will run without agent discovery.
)

REM ---------------------------------------------------------------------------
REM 3. MARKETPLACE
REM ---------------------------------------------------------------------------
echo [3/4] Starting Agent Marketplace on port %MARKETPLACE_PORT%...
start "Agent Marketplace (port %MARKETPLACE_PORT%)" cmd /k "cd /d %MARKETPLACE_DIR% && %MARKETPLACE_CMD%"
timeout /t 5 /nobreak >nul

REM ---------------------------------------------------------------------------
REM 4. DEMO AGENTS (optional)
REM ---------------------------------------------------------------------------
if "%START_DEMO_AGENTS%"=="1" (
    echo [4/4] Starting demo agents...

    if exist "%DEMO_CREDIT_DIR%\agent.py" (
        start "Demo: Credit Decision Agent (port 8201)" cmd /k "cd /d %DEMO_CREDIT_DIR% && python agent.py"
        timeout /t 2 /nobreak >nul
    ) else (
        echo [SKIP] Credit Decision Agent not found
    )

    if exist "%DEMO_KYC_DIR%\agent.py" (
        start "Demo: KYC Verification Agent (port 8202)" cmd /k "cd /d %DEMO_KYC_DIR% && python agent.py"
        timeout /t 2 /nobreak >nul
    ) else (
        echo [SKIP] KYC Verification Agent not found
    )
) else (
    echo [4/4] Skipping demo agents (START_DEMO_AGENTS=0)
)

REM ---------------------------------------------------------------------------
REM DONE
REM ---------------------------------------------------------------------------
echo.
echo ============================================================================
echo  All services started. Opening browser...
echo ============================================================================
echo.
echo   MCP Server          : http://localhost:%MCP_SERVER_PORT%
echo   A2A Server          : http://localhost:%A2A_SERVER_PORT%
echo   Agent Marketplace   : http://localhost:%MARKETPLACE_PORT%
if "%START_DEMO_AGENTS%"=="1" (
    echo   Credit Decision Agent : http://localhost:8201
    echo   KYC Verification Agent: http://localhost:8202
)
echo.
echo   Close the server windows to stop, or run stop.bat
echo ============================================================================

start http://localhost:%MARKETPLACE_PORT%
