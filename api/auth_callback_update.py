# OAuth callback update for main.py
# This code should replace the existing OAuth callback handlers

@app.get("/api/auth/google/callback")
async def google_auth_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db)
):
    """Handle Google OAuth callback and redirect to dashboard"""
    try:
        # Exchange code for tokens
        tokens = await exchange_google_code(code, state)
        
        # Get user info
        user_info = await get_google_user_info(tokens['access_token'])
        
        # Create or update user
        user = get_or_create_user(
            db, 
            email=user_info['email'],
            name=user_info.get('name'),
            picture=user_info.get('picture'),
            provider="google"
        )
        
        # Store OAuth tokens
        store_oauth_tokens(
            db,
            user.id,
            "google",
            tokens['access_token'],
            tokens.get('refresh_token'),
            tokens.get('expires_in')
        )
        
        # Trigger initial email sync
        try:
            logger.info(f"Starting initial email sync for user {user.email}")
            result = gmail_service.fetch_emails(db, user, max_results=50)
            logger.info(f"Initial sync completed: {len(result['emails'])} emails fetched")
        except Exception as sync_error:
            logger.error(f"Initial sync failed: {sync_error}")
        
        # Create JWT tokens
        access_token = create_access_token(data={"sub": user.email})
        refresh_token = create_refresh_token(data={"sub": user.email})
        
        # Determine redirect URL based on environment
        frontend_url = os.getenv("FRONTEND_URL", "http://www.saigbox.com")
        dashboard_url = os.getenv("DASHBOARD_URL", "https://dashboard.saigbox.com")
        
        # Redirect to login page with token, which will then redirect to dashboard
        redirect_url = f"{frontend_url}/login?token={access_token}&refresh={refresh_token}"
        
        return RedirectResponse(url=redirect_url)
        
    except Exception as e:
        logger.error(f"Google auth callback error: {e}")
        frontend_url = os.getenv("FRONTEND_URL", "http://www.saigbox.com")
        return RedirectResponse(url=f"{frontend_url}/login?error=auth_failed")

@app.get("/api/auth/microsoft/callback")
async def microsoft_auth_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db)
):
    """Handle Microsoft OAuth callback and redirect to dashboard"""
    try:
        # Exchange code for tokens
        tokens = await exchange_microsoft_code(code, state)
        
        # Get user info
        user_info = await get_microsoft_user_info(tokens['access_token'])
        
        # Create or update user
        user = get_or_create_user(
            db,
            email=user_info.get('mail') or user_info.get('userPrincipalName'),
            name=user_info.get('displayName'),
            provider="microsoft"
        )
        
        # Store OAuth tokens
        store_oauth_tokens(
            db,
            user.id,
            "microsoft",
            tokens['access_token'],
            tokens.get('refresh_token'),
            tokens.get('expires_in')
        )
        
        # Create JWT tokens
        access_token = create_access_token(data={"sub": user.email})
        refresh_token = create_refresh_token(data={"sub": user.email})
        
        # Determine redirect URL based on environment
        frontend_url = os.getenv("FRONTEND_URL", "http://www.saigbox.com")
        dashboard_url = os.getenv("DASHBOARD_URL", "https://dashboard.saigbox.com")
        
        # Redirect to login page with token, which will then redirect to dashboard
        redirect_url = f"{frontend_url}/login?token={access_token}&refresh={refresh_token}"
        
        return RedirectResponse(url=redirect_url)
        
    except Exception as e:
        logger.error(f"Microsoft auth callback error: {e}")
        frontend_url = os.getenv("FRONTEND_URL", "http://www.saigbox.com")
        return RedirectResponse(url=f"{frontend_url}/login?error=auth_failed")