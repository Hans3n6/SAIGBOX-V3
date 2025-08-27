#!/bin/bash

# Map Amplify environment variables to expected names
export AWS_COGNITO_USER_POOL_ID="${COGNITO_USER_POOL_ID:-$AWS_COGNITO_USER_POOL_ID}"
export AWS_COGNITO_CLIENT_ID="${COGNITO_CLIENT_ID:-$AWS_COGNITO_CLIENT_ID}"
export AWS_COGNITO_CLIENT_SECRET="${COGNITO_CLIENT_SECRET:-$AWS_COGNITO_CLIENT_SECRET}"
export AWS_COGNITO_DOMAIN="${COGNITO_DOMAIN:-$AWS_COGNITO_DOMAIN}"

# Set AWS credentials from renamed variables if present
if [ ! -z "$BEDROCK_ACCESS_KEY" ]; then
    export AWS_ACCESS_KEY_ID="$BEDROCK_ACCESS_KEY"
fi
if [ ! -z "$BEDROCK_SECRET_KEY" ]; then
    export AWS_SECRET_ACCESS_KEY="$BEDROCK_SECRET_KEY"
fi

# Ensure AWS_REGION is set
export AWS_REGION="${AWS_REGION:-us-east-1}"

# Set OAuth variables for compatibility
export OAUTH_GMAIL_CLIENT_ID="${GMAIL_CLIENT_ID}"
export OAUTH_GMAIL_CLIENT_SECRET="${GMAIL_CLIENT_SECRET}"
export UNIVERSAL_GMAIL_CLIENT_ID="${GMAIL_CLIENT_ID}"
export UNIVERSAL_GMAIL_CLIENT_SECRET="${GMAIL_CLIENT_SECRET}"

# Start the application
exec uvicorn api.main:app --host 0.0.0.0 --port 8000