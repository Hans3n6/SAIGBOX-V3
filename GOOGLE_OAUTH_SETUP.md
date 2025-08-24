# Google OAuth Setup Guide for SAIGBOX V3

## Fixing "Error 401: invalid_client"

This error occurs when Google OAuth credentials are misconfigured. Follow these steps to fix it:

## Step 1: Create/Update Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the Gmail API:
   - Go to "APIs & Services" > "Library"
   - Search for "Gmail API"
   - Click on it and press "Enable"

## Step 2: Create OAuth 2.0 Credentials

1. Go to "APIs & Services" > "Credentials"
2. Click "Create Credentials" > "OAuth client ID"
3. If prompted, configure the OAuth consent screen first:
   - Choose "External" for user type (unless using Google Workspace)
   - Fill in required fields (app name, support email, etc.)
   - Add scopes:
     - `openid`
     - `email`
     - `profile`
     - `https://www.googleapis.com/auth/gmail.readonly`
     - `https://www.googleapis.com/auth/gmail.modify`
     - `https://www.googleapis.com/auth/gmail.send`
   - Add test users if in testing mode

4. For the OAuth client:
   - Application type: **Web application**
   - Name: SAIGBOX V3
   - Authorized JavaScript origins:
     - `http://localhost:8000`
     - `http://localhost:3000` (if using separate frontend)
   - Authorized redirect URIs:
     - `http://localhost:8000/api/auth/google/callback`
     - Add any production URLs when deploying

5. Click "Create" and copy the Client ID and Client Secret

## Step 3: Update Your .env File

```bash
GMAIL_CLIENT_ID=your_actual_client_id_here.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=your_actual_client_secret_here
GMAIL_REDIRECT_URI=http://localhost:8000/api/auth/google/callback
```

## Step 4: Verify Configuration

1. Make sure the Client ID ends with `.apps.googleusercontent.com`
2. Ensure the redirect URI in .env EXACTLY matches what's in Google Cloud Console
3. The client secret should be the full string (usually starts with `GOCSPX-` for newer apps)

## Step 5: Restart the Backend

```bash
# Kill the existing process
pkill -f "uvicorn api.main:app"

# Restart with new environment variables
python3 -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

## Common Issues and Solutions

### Issue 1: "invalid_client" Error
- **Cause**: Wrong client ID or secret
- **Solution**: Copy credentials directly from Google Cloud Console, avoid manual typing

### Issue 2: "redirect_uri_mismatch" Error
- **Cause**: Redirect URI doesn't match
- **Solution**: Ensure the URI in .env matches EXACTLY (including http vs https, port, path)

### Issue 3: "access_blocked" Error
- **Cause**: App not verified or scopes not approved
- **Solution**: Add your email as a test user in OAuth consent screen

### Issue 4: Credentials Don't Work
- **Cause**: Using wrong project or deleted credentials
- **Solution**: Create new credentials in the correct project

## Testing the Fix

1. Clear browser cookies/cache for localhost
2. Go to http://localhost:8000/login
3. Click "Continue with Google"
4. You should see Google's consent screen
5. Authorize the app
6. You'll be redirected back to SAIGBOX

## For Production Deployment

When deploying to production:
1. Update redirect URIs in Google Cloud Console
2. Update .env with production URLs
3. Consider getting OAuth app verified by Google for public use