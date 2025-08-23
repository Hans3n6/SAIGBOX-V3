# OAuth Setup Guide for SAIGBOX V3

## Overview

SAIGBOX V3 uses OAuth 2.0 to securely access user email accounts. Users authenticate directly with their email provider (Google/Microsoft) and grant SAIGBOX permission to access their emails. No email passwords are ever stored by SAIGBOX.

## How It Works

### Authentication Flow

1. **User visits SAIGBOX** → Redirected to `/auth` login page
2. **User selects provider** → Clicks "Continue with Google" or "Continue with Microsoft"
3. **OAuth consent** → User is redirected to provider's OAuth consent screen
4. **User grants permissions** → User approves email access for SAIGBOX
5. **Tokens received** → SAIGBOX receives OAuth tokens (access & refresh tokens)
6. **Tokens stored securely** → Tokens are encrypted and stored in the database
7. **Access granted** → User can now use SAIGBOX with their email account

### Token Management

- **Access tokens**: Used to make API calls to Gmail/Outlook (typically expire in 1 hour)
- **Refresh tokens**: Used to get new access tokens when they expire (long-lived)
- **Automatic refresh**: SAIGBOX automatically refreshes expired tokens
- **Secure storage**: All tokens are stored encrypted in the database per user

## Setting Up OAuth Applications

### Google OAuth Setup

1. **Go to Google Cloud Console**
   - Visit https://console.cloud.google.com/
   - Create a new project or select existing one

2. **Enable Gmail API**
   - Go to "APIs & Services" → "Library"
   - Search for "Gmail API"
   - Click Enable

3. **Create OAuth Credentials**
   - Go to "APIs & Services" → "Credentials"
   - Click "Create Credentials" → "OAuth client ID"
   - Choose "Web application"
   - Add authorized redirect URIs:
     - `http://localhost:8000/api/auth/google/callback` (development)
     - `https://yourdomain.com/api/auth/google/callback` (production)

4. **Configure OAuth Consent Screen**
   - Go to "OAuth consent screen"
   - Choose "External" user type
   - Fill in app information
   - Add scopes:
     - `email`
     - `profile`
     - `openid`
     - `https://www.googleapis.com/auth/gmail.readonly`
     - `https://www.googleapis.com/auth/gmail.modify`
     - `https://www.googleapis.com/auth/gmail.compose`
     - `https://www.googleapis.com/auth/gmail.send`

5. **Copy Credentials**
   ```env
   GMAIL_CLIENT_ID=your_client_id_here
   GMAIL_CLIENT_SECRET=your_client_secret_here
   GMAIL_REDIRECT_URI=http://localhost:8000/api/auth/google/callback
   ```

### Microsoft OAuth Setup

1. **Go to Azure Portal**
   - Visit https://portal.azure.com/
   - Go to "Azure Active Directory" → "App registrations"

2. **Register New Application**
   - Click "New registration"
   - Name: "SAIGBOX"
   - Supported account types: "Personal Microsoft accounts only"
   - Redirect URI: `http://localhost:8000/api/auth/microsoft/callback`

3. **Configure API Permissions**
   - Go to "API permissions"
   - Add permissions:
     - Microsoft Graph:
       - `email`
       - `profile`
       - `openid`
       - `offline_access`
       - `Mail.ReadWrite`
       - `Mail.Send`

4. **Create Client Secret**
   - Go to "Certificates & secrets"
   - Click "New client secret"
   - Copy the secret value immediately

5. **Copy Credentials**
   ```env
   MICROSOFT_CLIENT_ID=your_application_id_here
   MICROSOFT_CLIENT_SECRET=your_client_secret_here
   MICROSOFT_REDIRECT_URI=http://localhost:8000/api/auth/microsoft/callback
   ```

## Environment Variables

Create a `.env` file in the project root:

```env
# OAuth App Credentials (YOUR app, not user credentials)
GMAIL_CLIENT_ID=xxx.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=GOCSPX-xxx
GMAIL_REDIRECT_URI=http://localhost:8000/api/auth/google/callback

MICROSOFT_CLIENT_ID=xxx-xxx-xxx
MICROSOFT_CLIENT_SECRET=xxx
MICROSOFT_REDIRECT_URI=http://localhost:8000/api/auth/microsoft/callback

# JWT for session management
SECRET_KEY=your_secure_random_string_here
ALGORITHM=HS256

# Database
DATABASE_URL=sqlite:///saigbox.db
```

## Security Best Practices

1. **Never store user passwords** - Only OAuth tokens
2. **Use HTTPS in production** - Protect token transmission
3. **Encrypt tokens at rest** - Use encryption for database storage
4. **Implement token rotation** - Refresh tokens regularly
5. **Limit scope access** - Only request necessary permissions
6. **Secure client secrets** - Never commit secrets to version control

## Testing OAuth Flow

1. **Start the application**
   ```bash
   python3 -m uvicorn api.main:app --reload
   ```

2. **Visit login page**
   - Go to http://localhost:8000/auth

3. **Test Google OAuth**
   - Click "Continue with Google"
   - Sign in with Google account
   - Grant permissions
   - Should redirect to main app

4. **Test Microsoft OAuth**
   - Click "Continue with Microsoft"
   - Sign in with Microsoft account
   - Grant permissions
   - Should redirect to main app

5. **Test Demo Mode**
   - Click "Try Demo Mode"
   - Creates a demo session without real email access

## Troubleshooting

### "Redirect URI mismatch" error
- Ensure redirect URI in `.env` matches exactly what's configured in Google/Azure
- Check for trailing slashes, http vs https

### "Invalid client" error
- Verify CLIENT_ID and CLIENT_SECRET are correct
- Ensure OAuth app is not in test mode with limited users

### Tokens expired
- SAIGBOX should automatically refresh tokens
- If not working, user may need to re-authenticate

### No emails loading
- Check if user granted all required permissions
- Verify Gmail/Outlook API is enabled
- Check token validity in database

## Production Deployment

1. **Update redirect URIs** to use your domain
2. **Use HTTPS** for all OAuth endpoints
3. **Encrypt tokens** before database storage
4. **Set secure cookie flags** in production
5. **Implement rate limiting** for OAuth endpoints
6. **Monitor token usage** and implement alerts

## Support

For issues with OAuth setup, check:
- Google OAuth documentation: https://developers.google.com/identity/protocols/oauth2
- Microsoft OAuth documentation: https://docs.microsoft.com/en-us/azure/active-directory/develop/
- SAIGBOX Issues: https://github.com/yourusername/saigbox-v3/issues