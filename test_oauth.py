#!/usr/bin/env python3
"""Test OAuth configuration and authentication flow"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_oauth_config():
    """Test if OAuth configuration is properly loaded"""
    print("Testing OAuth Configuration...")
    print("=" * 50)
    
    # Check Google OAuth credentials
    gmail_client_id = os.getenv("GMAIL_CLIENT_ID")
    gmail_client_secret = os.getenv("GMAIL_CLIENT_SECRET")
    gmail_redirect_uri = os.getenv("GMAIL_REDIRECT_URI")
    
    print("\n1. Google OAuth Configuration:")
    print(f"   Client ID: {'✓ Set' if gmail_client_id else '✗ Missing'}")
    if gmail_client_id:
        print(f"      - Value: {gmail_client_id[:20]}...")
    print(f"   Client Secret: {'✓ Set' if gmail_client_secret else '✗ Missing'}")
    if gmail_client_secret:
        print(f"      - Value: {gmail_client_secret[:10]}...")
    print(f"   Redirect URI: {'✓ Set' if gmail_redirect_uri else '✗ Missing'}")
    if gmail_redirect_uri:
        print(f"      - Value: {gmail_redirect_uri}")
    
    # Check JWT configuration
    secret_key = os.getenv("SECRET_KEY")
    algorithm = os.getenv("ALGORITHM")
    
    print("\n2. JWT Configuration:")
    print(f"   Secret Key: {'✓ Set' if secret_key else '✗ Missing'}")
    print(f"   Algorithm: {algorithm if algorithm else '✗ Missing'}")
    
    # Test OAuth manager initialization
    print("\n3. Testing OAuth Manager Initialization...")
    try:
        from core.oauth_config import oauth_manager, OAuthProvider
        
        # Check if Google provider is initialized
        google_provider = oauth_manager.get_provider(OAuthProvider.GOOGLE.value)
        if google_provider:
            print("   ✓ Google OAuth provider initialized")
            print(f"      - Auth URL: {google_provider.auth_url}")
            print(f"      - Token URL: {google_provider.token_url}")
            print(f"      - Scopes: {len(google_provider.scopes)} scopes configured")
        else:
            print("   ✗ Google OAuth provider not initialized")
            
    except Exception as e:
        print(f"   ✗ Error initializing OAuth manager: {e}")
    
    # Test auth URL generation
    print("\n4. Testing OAuth URL Generation...")
    try:
        from api.auth import get_google_oauth_url
        
        auth_url = get_google_oauth_url()
        if auth_url:
            print(f"   ✓ OAuth URL generated successfully")
            print(f"      - URL length: {len(auth_url)} characters")
            # Check if URL contains required parameters
            if "client_id=" in auth_url:
                print("      - Contains client_id: ✓")
            if "redirect_uri=" in auth_url:
                print("      - Contains redirect_uri: ✓")
            if "scope=" in auth_url:
                print("      - Contains scope: ✓")
            if "state=" in auth_url:
                print("      - Contains state (CSRF protection): ✓")
        else:
            print("   ✗ Failed to generate OAuth URL")
            
    except Exception as e:
        print(f"   ✗ Error generating OAuth URL: {e}")
    
    # Test database connection
    print("\n5. Testing Database Connection...")
    try:
        from core.database import engine, SessionLocal
        from sqlalchemy import text
        
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("   ✓ Database connection successful")
            
        # Check if users table exists
        from core.database import User
        db = SessionLocal()
        try:
            user_count = db.query(User).count()
            print(f"   ✓ Users table exists ({user_count} users)")
        except Exception as e:
            print(f"   ✗ Error accessing users table: {e}")
        finally:
            db.close()
            
    except Exception as e:
        print(f"   ✗ Database error: {e}")
    
    print("\n" + "=" * 50)
    print("OAuth Configuration Test Complete")
    
    # Summary
    all_good = all([
        gmail_client_id,
        gmail_client_secret,
        gmail_redirect_uri,
        secret_key,
        algorithm
    ])
    
    if all_good:
        print("\n✓ All required configurations are set!")
        print("\nYou should be able to authenticate. If not, check:")
        print("1. Google Cloud Console OAuth settings")
        print("2. Authorized redirect URIs match exactly")
        print("3. OAuth consent screen is configured")
    else:
        print("\n✗ Some configurations are missing. Please check your .env file")
    
    return all_good

if __name__ == "__main__":
    test_oauth_config()