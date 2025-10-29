#!/bin/bash

echo "🚀 Starting Nate's Discord Integration on Railway"
echo "=================================================="

# Start MCP server in background (it will pre-load channels automatically)
echo "🔌 Starting MCP Server on port 8000..."
python mcp_server.py &
MCP_PID=$!
echo "✓ MCP Server running (PID: $MCP_PID)"

# Wait for MCP server to fully initialize
sleep 8

# Start Action server (this blocks and keeps container alive)
echo ""
echo "🎯 Starting Action Server on port ${PORT:-3000}..."
exec gunicorn -w 4 -b 0.0.0.0:${PORT:-3000} action_server:app --access-logfile - --error-logfile -