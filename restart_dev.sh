#!/bin/bash

# Restart the development server (useful after code changes in stable mode)

echo "🔄 Restarting SAIGBOX development server..."

# Kill existing process
pkill -f "uvicorn api.main:app" 2>/dev/null
sleep 1

# Start again
./start_dev.sh