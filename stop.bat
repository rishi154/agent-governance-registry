@echo off
REM ============================================================================
REM Agent Marketplace — Stop All Services
REM ============================================================================
echo Stopping all Agent Marketplace services...
echo.

REM Kill by window title (matches the titles set in startup.bat)
taskkill /FI "WINDOWTITLE eq MCP Server*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq A2A Server*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Agent Marketplace*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Demo: Credit*" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Demo: KYC*" /F >nul 2>&1

REM Also kill by port in case windows were renamed
for %%p in (9595 9000 8500 8201 8202) do (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr :%%p ^| findstr LISTENING 2^>nul') do (
        taskkill /PID %%a /F >nul 2>&1
    )
)

echo All services stopped.
