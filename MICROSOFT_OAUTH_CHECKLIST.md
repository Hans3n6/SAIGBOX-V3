# Microsoft OAuth Configuration Checklist

## Prerequisites
- Azure Portal access
- Your Application (client) ID from the .env file
- Your Directory (tenant) ID

## Step-by-Step Configuration

### 1. Access Azure Portal
- URL: https://portal.azure.com/
- Sign in with your Microsoft account

### 2. Navigate to App Registration
- Go to **Azure Active Directory**
- Click **App registrations**
- Find your app (should match the Application ID in your .env file)
- Click on your app name

### 3. Configure Authentication
- Click **Authentication** in the left menu
- Under **Platform configurations**, find **Web**
- If Web platform doesn't exist, click **Add a platform** → **Web**

### 4. Update Redirect URIs
Add ALL of the following URLs:
```
https://api.saigbox.com/api/auth/microsoft/callback
http://www.saigbox.com/api/auth/microsoft/callback
https://www.saigbox.com/api/auth/microsoft/callback
http://localhost:8000/api/auth/microsoft/callback
```

### 5. Configure Supported Account Types
- Select: **Accounts in any organizational directory (Any Azure AD directory - Multitenant) and personal Microsoft accounts**
- This allows both work/school and personal Microsoft accounts

### 6. Configure Implicit Grant
- Check both:
  - ✅ Access tokens (used for implicit flows)
  - ✅ ID tokens (used for implicit and hybrid flows)

### 7. Save Changes
- Click **Save** at the top
- Changes may take 1-5 minutes to propagate

## Verification Steps
1. Clear browser cache and cookies
2. Go to http://www.saigbox.com/login
3. Click "Continue with Microsoft"
4. Should redirect to Microsoft login
5. After login, should return to dashboard

## Common Issues & Solutions

### Issue: AADSTS50011 - Redirect URI mismatch
- **Solution**: Ensure ALL redirect URIs are added exactly as shown
- Check for trailing slashes (there should be none)
- Wait 5 minutes for propagation

### Issue: AADSTS700016 - Application not found
- **Solution**: Verify Application ID matches the one in .env file
- Check tenant ID is correct

### Issue: AADSTS50194 - Application is not configured as multi-tenant
- **Solution**: Change supported account types to multitenant + personal accounts

## Current Configuration in Code
- Backend: `https://api.saigbox.com`
- Frontend: `http://www.saigbox.com`
- Dashboard: `https://dashboard.saigbox.com`
- Tenant: Common (for multitenant)