#!/bin/bash

# SAIGBOX V3 Server Startup Script
# This script ensures the correct environment variables are set

cd "$(dirname "$0")"

# Activate virtual environment
source venv/bin/activate

# Load environment variables from .env file
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Set AWS Bedrock flag
export USE_BEDROCK=true

# Start the server
echo "Starting SAIGBOX V3 with AWS Bedrock..."
echo "USE_BEDROCK=${USE_BEDROCK}"
echo "AWS_REGION=${AWS_REGION}"
echo "Server will be available at http://localhost:8000"
echo ""

uvicorn api.main:app --reload
