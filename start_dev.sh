#!/bin/bash

# Start development server WITHOUT auto-reload for stability
# Use this when you want the server to stay running during code edits

echo "🚀 Starting SAIGBOX development server (stable mode - no auto-reload)..."

# Kill any existing uvicorn processes
pkill -f "uvicorn api.main:app" 2>/dev/null

# Activate virtual environment and start server
source venv/bin/activate
nohup uvicorn api.main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &

PID=$!
echo "✅ Server started successfully!"
echo "   PID: $PID"
echo "   URL: http://localhost:8000"
echo "   Logs: tail -f server.log"
echo ""
echo "⚠️  Note: Server will NOT auto-restart on code changes."
echo "   Run './restart_dev.sh' to manually restart after changes."