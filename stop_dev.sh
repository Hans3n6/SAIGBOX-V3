#!/bin/bash

# Stop the development server

echo "🛑 Stopping SAIGBOX development server..."

# Kill uvicorn process
pkill -f "uvicorn api.main:app"

if [ $? -eq 0 ]; then
    echo "✅ Server stopped successfully"
else
    echo "⚠️  No server process found"
fi