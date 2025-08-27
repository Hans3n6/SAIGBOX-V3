const { spawn } = require('child_process');
const path = require('path');

// Map Amplify environment variables to expected names
const envMapping = {
  'COGNITO_USER_POOL_ID': 'AWS_COGNITO_USER_POOL_ID',
  'COGNITO_CLIENT_ID': 'AWS_COGNITO_CLIENT_ID',
  'COGNITO_CLIENT_SECRET': 'AWS_COGNITO_CLIENT_SECRET',
  'COGNITO_DOMAIN': 'AWS_COGNITO_DOMAIN',
  'BEDROCK_ACCESS_KEY': 'AWS_ACCESS_KEY_ID',
  'BEDROCK_SECRET_KEY': 'AWS_SECRET_ACCESS_KEY'
};

// Set up environment variables
Object.keys(envMapping).forEach(key => {
  if (process.env[key]) {
    process.env[envMapping[key]] = process.env[key];
  }
});

// Ensure AWS_REGION is set
process.env.AWS_REGION = process.env.AWS_REGION || 'us-east-1';

// Set OAuth variables for compatibility
if (process.env.GMAIL_CLIENT_ID) {
  process.env.OAUTH_GMAIL_CLIENT_ID = process.env.GMAIL_CLIENT_ID;
  process.env.UNIVERSAL_GMAIL_CLIENT_ID = process.env.GMAIL_CLIENT_ID;
}
if (process.env.GMAIL_CLIENT_SECRET) {
  process.env.OAUTH_GMAIL_CLIENT_SECRET = process.env.GMAIL_CLIENT_SECRET;
  process.env.UNIVERSAL_GMAIL_CLIENT_SECRET = process.env.GMAIL_CLIENT_SECRET;
}

const port = process.env.PORT || 8000;
console.log(`Starting FastAPI server on port ${port}...`);

// Start the FastAPI application
const fastapi = spawn('uvicorn', [
  'api.main:app',
  '--host', '0.0.0.0',
  '--port', port.toString()
], {
  env: process.env,
  stdio: 'inherit'
});

fastapi.on('error', (err) => {
  console.error('Failed to start FastAPI server:', err);
  process.exit(1);
});

fastapi.on('exit', (code) => {
  console.log(`FastAPI server exited with code ${code}`);
  process.exit(code);
});