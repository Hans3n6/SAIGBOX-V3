# Outlook/Microsoft Email Support Setup Guide

SAIGBOX now supports Microsoft/Outlook email accounts alongside Gmail. This guide will help you configure Microsoft OAuth and enable Outlook email sync.

## Prerequisites

1. Microsoft Azure account (free tier is sufficient)
2. An active Microsoft 365 or Outlook.com email account
3. Admin access to your SAIGBOX deployment

## Step 1: Register Application in Azure AD

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** → **App registrations**
3. Click **New registration**
4. Configure the application:
   - **Name**: SAIGBOX Email Manager (or your preferred name)
   - **Supported account types**: 
     - Choose "Accounts in any organizational directory and personal Microsoft accounts" for broadest support
     - Or select based on your needs
   - **Redirect URI**: 
     - Platform: Web
     - URI: `https://your-domain.com/api/auth/microsoft/callback`
5. Click **Register**

## Step 2: Configure Application Permissions

1. In your app registration, go to **API permissions**
2. Click **Add a permission** → **Microsoft Graph**
3. Choose **Delegated permissions**
4. Add the following permissions:
   - `Mail.ReadWrite` - Read and write user mail
   - `Mail.Send` - Send mail as the user
   - `User.Read` - Sign in and read user profile
   - `offline_access` - Maintain access to data
5. Click **Add permissions**
6. Click **Grant admin consent** (if you're an admin)

## Step 3: Create Client Secret

1. Go to **Certificates & secrets**
2. Click **New client secret**
3. Add a description (e.g., "SAIGBOX Production")
4. Choose expiration period (recommend 24 months)
5. Click **Add**
6. **IMPORTANT**: Copy the secret value immediately (you won't see it again)

## Step 4: Get Application IDs

From the **Overview** page, copy:
- **Application (client) ID** - This is your `MICROSOFT_CLIENT_ID`
- **Directory (tenant) ID** - This is your `MICROSOFT_TENANT_ID`

## Step 5: Configure SAIGBOX Environment

1. Edit your `.env` file:

```bash
# Microsoft OAuth Configuration
MICROSOFT_CLIENT_ID=your-application-client-id
MICROSOFT_CLIENT_SECRET=your-client-secret-value
MICROSOFT_TENANT_ID=your-tenant-id  # or "common" for multi-tenant
MICROSOFT_REDIRECT_URI=https://your-domain.com/api/auth/microsoft/callback
```

2. Update the redirect URI in your Azure app registration to match exactly

## Step 6: Run Database Migration

```bash
# Run the migration to add Outlook support columns
python migrations/add_outlook_support.py
```

## Step 7: Restart SAIGBOX

```bash
# If using systemd
sudo systemctl restart saigbox

# If using Docker
docker-compose restart

# If running locally
# Stop the server (Ctrl+C) and restart
python -m uvicorn api.main:app --reload
```

## Step 8: Test Microsoft Login

1. Navigate to your SAIGBOX login page
2. Click "Continue with Microsoft"
3. Sign in with your Microsoft account
4. Grant permissions when prompted
5. You should be redirected back to SAIGBOX inbox

## Supported Features

With Outlook integration, SAIGBOX supports:

- ✅ Email synchronization (inbox, sent, drafts)
- ✅ Moving emails to trash
- ✅ Restoring emails from trash
- ✅ Permanently deleting emails
- ✅ Creating folders
- ✅ Moving emails between folders
- ✅ Sending emails
- ✅ Urgency detection
- ✅ Automatic action item creation
- ✅ SAIG AI assistant for Outlook emails

## Troubleshooting

### "Invalid client" error
- Verify your `MICROSOFT_CLIENT_ID` is correct
- Check that the redirect URI matches exactly (including https://)

### "Invalid client secret" error
- Regenerate the client secret in Azure
- Update your `.env` file with the new secret
- Restart SAIGBOX

### Emails not syncing
- Check that Mail.ReadWrite permission is granted
- Verify the user has consented to permissions
- Check logs: `sudo journalctl -u saigbox -n 50`

### Token expiration issues
- Ensure `offline_access` permission is granted
- Check that refresh tokens are being stored properly
- Verify database has write permissions

## API Rate Limits

Microsoft Graph API has rate limits:
- 10,000 requests per 10 minutes per app per tenant
- SAIGBOX implements automatic retry with exponential backoff
- Large mailboxes are synced in batches

## Security Considerations

1. **Client Secret**: Keep your client secret secure and rotate it regularly
2. **Permissions**: Only request permissions you need
3. **Token Storage**: Tokens are encrypted in the database
4. **HTTPS**: Always use HTTPS for redirect URIs
5. **Tenant Restrictions**: Consider restricting to specific tenants if needed

## Multiple Email Accounts

Users can connect both Gmail and Outlook accounts:
1. First sign in with one provider (e.g., Google)
2. In settings, click "Add email account"
3. Choose the other provider (e.g., Microsoft)
4. Emails from both accounts will be merged in the inbox

## Support

For issues or questions:
- Check logs: `sudo journalctl -u saigbox -f`
- Review Azure AD sign-in logs
- Open an issue on GitHub with details (exclude sensitive info)