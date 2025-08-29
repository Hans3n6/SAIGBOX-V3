#!/bin/bash

# Start development server WITH auto-reload
# Use this when you want the server to auto-restart on code changes

echo "🚀 Starting SAIGBOX development server (auto-reload mode)..."
echo "⚠️  Warning: Server will restart automatically when you edit code!"

# Kill any existing uvicorn processes
pkill -f "uvicorn api.main:app" 2>/dev/null

# Activate virtual environment and start server with reload
source venv/bin/activate
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000