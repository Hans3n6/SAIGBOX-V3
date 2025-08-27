# Google OAuth Configuration Checklist

## Your Current Configuration
- **Client ID**: `575785369129-d03aj6b4qekuu2bbje4mj6omu2mr1j1n.apps.googleusercontent.com`
- **Redirect URI**: `http://localhost:8000/api/auth/google/callback`

## Steps to Verify in Google Cloud Console

### 1. Go to Google Cloud Console
Visit: https://console.cloud.google.com/

### 2. Select Your Project
Make sure you're in the correct project where you created the OAuth credentials.

### 3. Check OAuth Consent Screen
Go to **APIs & Services** → **OAuth consent screen**

Verify the following:
- [ ] **Publishing status**: Should be "Testing" or "In production"
- [ ] **User type**: External or Internal
- [ ] **Test users** (if in Testing mode): Your email should be listed

If in Testing mode, you MUST add your email as a test user:
1. Click on "ADD USERS" button
2. Enter your Gmail address
3. Click Save

### 4. Verify OAuth 2.0 Client ID Settings
Go to **APIs & Services** → **Credentials**

Click on your OAuth 2.0 Client ID (the one ending in `.apps.googleusercontent.com`)

Verify:
- [ ] **Application type**: Web application
- [ ] **Authorized JavaScript origins** includes:
  - `http://localhost:8000`
  - `http://localhost` (optional)

- [ ] **Authorized redirect URIs** includes EXACTLY:
  - `http://localhost:8000/api/auth/google/callback`
  
  ⚠️ **IMPORTANT**: This must match EXACTLY - no trailing slashes, same protocol (http/https), same port

### 5. Check Gmail API Status
Go to **APIs & Services** → **Enabled APIs**

Verify:
- [ ] Gmail API is listed and enabled

If not enabled:
1. Go to **APIs & Services** → **Library**
2. Search for "Gmail API"
3. Click on it and press "ENABLE"

### 6. Check Scopes
Go to **APIs & Services** → **OAuth consent screen** → **Scopes**

Verify these scopes are added:
- [ ] `.../auth/userinfo.email`
- [ ] `.../auth/userinfo.profile`
- [ ] `openid`
- [ ] `https://www.googleapis.com/auth/gmail.readonly`
- [ ] `https://www.googleapis.com/auth/gmail.modify`
- [ ] `https://www.googleapis.com/auth/gmail.compose`
- [ ] `https://www.googleapis.com/auth/gmail.send`

## Common Issues and Solutions

### Issue: "Access blocked: This app's request is invalid"
**Solution**: You're missing test users. Add your email to test users list.

### Issue: "Error 400: redirect_uri_mismatch"
**Solution**: The redirect URI in Google Console doesn't match exactly. Common mistakes:
- Wrong port (8000 vs 8080)
- Wrong protocol (http vs https)
- Trailing slash difference
- Different subdomain

### Issue: "Error 400: invalid_request"
**Solution**: OAuth consent screen is not configured. Complete the consent screen setup.

### Issue: Authentication succeeds but returns to login
**Solution**: Cookie/session issue. Check browser console for errors.

## Quick Test

After verifying all above settings, test the OAuth flow:

1. Open Chrome Incognito window
2. Go to: http://localhost:8000/auth
3. Click "Continue with Google"
4. If you see Google's sign-in page, the client configuration is correct
5. After signing in, if you see permission consent screen, OAuth is working
6. Grant permissions and you should be redirected back to the app

## Still Not Working?

If authentication still fails after checking all above:

1. **Clear browser data** for localhost:8000
2. **Try a different browser** or incognito mode
3. **Check browser console** (F12) for JavaScript errors
4. **Check server logs**: `tail -f server.log`
5. **Regenerate credentials** in Google Cloud Console if needed

## Your Action Items

Based on your current setup, please check:

1. ✅ Your OAuth credentials are loaded correctly (verified)
2. ✅ The server is running on port 8000 (verified)
3. ⚠️ **CHECK**: Are you added as a test user in Google Console?
4. ⚠️ **CHECK**: Does the redirect URI match EXACTLY in Google Console?
5. ⚠️ **CHECK**: Is the OAuth consent screen configured?

The most likely issue is that you need to add your email as a test user if the app is in testing mode.