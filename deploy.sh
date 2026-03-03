#!/bin/bash
# Deployment script for agent-marketplace

set -e

echo "=== Agent Marketplace Deployment ==="

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python version: $python_version"

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Check for .env file
if [ ! -f .env ]; then
    echo "⚠ .env file not found. Creating from template..."
    cp .env.example .env
    echo "⚠ Please edit .env with your configuration before running"
    exit 1
fi

# Check for GCP credentials
if [ -z "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
    echo "⚠ GOOGLE_APPLICATION_CREDENTIALS not set"
    echo "  Set it with: export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json"
    exit 1
fi

if [ ! -f "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
    echo "⚠ GCP credentials file not found: $GOOGLE_APPLICATION_CREDENTIALS"
    exit 1
fi

echo "✓ GCP credentials found"

# Check if database exists
if [ -f marketplace.db ]; then
    echo "✓ Database exists"
else
    echo "✓ Database will be created on first run"
fi

# Check MCP server
echo "Checking MCP server..."
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✓ MCP server is running (port 8000)"
else
    echo "⚠ MCP server not detected on port 8000"
    echo "  Start it with: cd mcp-server && python server.py"
fi

# Check A2A server
echo "Checking A2A server..."
if curl -s http://localhost:9000/agents > /dev/null 2>&1; then
    echo "✓ A2A server is running (port 9000)"
else
    echo "⚠ A2A server not detected on port 9000"
    echo "  Start it with: cd a2a-server && python server.py"
fi

echo ""
echo "=== Deployment Complete ==="
echo "Run: python app.py"
echo "Access UI: http://localhost:8500"
