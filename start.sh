#!/bin/bash

echo "🚀 Starting Nate's Discord Integration on Railway"
echo "=================================================="

# Start MCP server in background
echo "🔌 Starting MCP Server on port 8000..."
uvicorn mcp_server:mcp --host 0.0.0.0 --port 8000 --log-level info &
MCP_PID=$!
echo "✓ MCP Server running (PID: $MCP_PID)"

# Wait for MCP server to be ready
sleep 3

# Pre-cache Nate's channels
echo ""
echo "📚 Pre-caching Nate's channels..."

# Storm-forge Journal
echo "  → Storm-forge Journal (1427374434150383726)"
curl -s -X POST http://localhost:8000/sse/refresh_cache \
  -H "Content-Type: application/json" \
  -d '{"channel_id": "1427374434150383726", "limit": 100}' > /dev/null

# Agent Tasks
echo "  → Agent Tasks (1425961804823003146)"
curl -s -X POST http://localhost:8000/sse/refresh_cache \
  -H "Content-Type: application/json" \
  -d '{"channel_id": "1425961804823003146", "limit": 100}' > /dev/null

# Stormlab Crew
echo "  → Stormlab Crew (1425543847340937236)"
curl -s -X POST http://localhost:8000/sse/refresh_cache \
  -H "Content-Type: application/json" \
  -d '{"channel_id": "1425543847340937236", "limit": 100}' > /dev/null

echo "✓ Channels cached"

# Start Action server (this blocks and keeps container alive)
echo ""
echo "🎯 Starting Action Server on port ${PORT:-3000}..."
exec gunicorn -w 4 -b 0.0.0.0:${PORT:-3000} action_server:app --access-logfile - --error-logfile -
