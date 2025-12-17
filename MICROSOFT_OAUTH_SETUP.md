# Microsoft OAuth Setup Guide

## Quick Setup

### Step 1: Get Your Azure Credentials

1. Go to [Azure Portal](https://portal.azure.com/)
2. Navigate to **Azure Active Directory** → **App registrations**
3. Click **New registration** (or select existing app)

### Step 2: Register Your Application

**Name:** SAIGBOX  
**Supported account types:** Accounts in any organizational directory and personal Microsoft accounts  
**Redirect URI:** Web → `http://localhost:8000/api/auth/microsoft/callback`

Click **Register**

### Step 3: Get Your Credentials

After registration:
1. **Application (client) ID**: Copy this from the Overview page
2. **Client Secret**: 
   - Go to **Certificates & secrets** → **Client secrets**
   - Click **New client secret**
   - Add description: "SAIGBOX OAuth"
   - Choose expiration (24 months recommended)
   - Click **Add**
   - **IMPORTANT**: Copy the **Value** immediately (not the Secret ID)

### Step 4: Configure Redirect URIs

Go to **Authentication** → **Platform configurations** → **Web**

Add these redirect URIs:
```
http://localhost:8000/api/auth/microsoft/callback
https://api.saigbox.com/api/auth/microsoft/callback
https://www.saigbox.com/api/auth/microsoft/callback
```

### Step 5: Run Setup Script

```bash
./setup_microsoft_oauth.sh
```

Enter your:
- Application (client) ID
- Client Secret Value

### Step 6: Restart Server

```bash
# Kill existing server
kill $(lsof -t -i:8000)

# Start server
python3 -m uvicorn api.main:app --reload --port 8000
```

## Manual Setup (Alternative)

Edit `.env` file and replace:
```env
MICROSOFT_CLIENT_ID=YOUR_AZURE_APP_CLIENT_ID_HERE
MICROSOFT_CLIENT_SECRET=YOUR_AZURE_APP_CLIENT_SECRET_HERE
```

With your actual values from Azure Portal.

## Verification

1. Go to http://localhost:8000/login
2. Click "Continue with Microsoft"
3. You should be redirected to Microsoft login
4. After authentication, you'll return to SAIGBOX

## Troubleshooting

### Error: "Microsoft OAuth not configured"
- Ensure MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET are set in .env
- Restart the server after updating .env

### Error: "AADSTS50011: Reply URL mismatch"
- Add the exact redirect URI to Azure Portal
- For local testing: `http://localhost:8000/api/auth/microsoft/callback`
- For production: `https://api.saigbox.com/api/auth/microsoft/callback`

### Error: "AADSTS700016: Application not found"
- Verify the Client ID matches exactly
- Check you're using the correct tenant (use "common" for multi-tenant)

## Required API Permissions

In Azure Portal → Your App → API permissions, ensure you have:
- Microsoft Graph:
  - `email` (delegated)
  - `openid` (delegated)
  - `profile` (delegated)
  - `Mail.ReadWrite` (delegated)
  - `Mail.Send` (delegated)
  - `offline_access` (delegated)

Click **Grant admin consent** if needed.