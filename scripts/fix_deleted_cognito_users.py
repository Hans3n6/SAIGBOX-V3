#!/usr/bin/env python3
"""
Script to fix users whose Cognito accounts were deleted
Clears orphaned Cognito references so they can be re-created
"""
import os
import sys
import asyncio

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.database import User
from core.cognito_auth import CognitoAuth

# Database setup
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./saigbox.db')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

async def check_and_fix_deleted_users():
    """Check all users with Cognito IDs and fix any that were deleted"""
    db = SessionLocal()
    cognito = CognitoAuth()
    
    try:
        # Get all users with Cognito IDs
        users_with_cognito = db.query(User).filter(
            User.cognito_sub.isnot(None)
        ).all()
        
        print(f"Checking {len(users_with_cognito)} users with Cognito accounts...")
        
        fixed_count = 0
        for user in users_with_cognito:
            # Check if the Cognito user still exists
            cognito_user = await cognito.get_user_info_by_sub(user.cognito_sub)
            
            if not cognito_user:
                # Cognito user was deleted, clear the reference
                print(f"❌ Cognito user deleted: {user.email} (sub: {user.cognito_sub})")
                user.cognito_sub = None
                user.cognito_confirmed = False
                user.cognito_access_token = None
                user.cognito_refresh_token = None
                user.cognito_temp_password = None
                fixed_count += 1
                print(f"   ✅ Cleared Cognito references for {user.email}")
            else:
                print(f"✅ Cognito user exists: {user.email}")
        
        if fixed_count > 0:
            db.commit()
            print(f"\n✅ Fixed {fixed_count} users with deleted Cognito accounts")
        else:
            print(f"\n✅ All users have valid Cognito accounts")
        
    finally:
        db.close()

async def fix_specific_user(email: str):
    """Fix a specific user whose Cognito account was deleted"""
    db = SessionLocal()
    
    try:
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            print(f"❌ User {email} not found in database")
            return
        
        if not user.cognito_sub:
            print(f"ℹ️ User {email} has no Cognito account")
            return
        
        print(f"Clearing Cognito references for {email}...")
        print(f"  Previous cognito_sub: {user.cognito_sub}")
        
        user.cognito_sub = None
        user.cognito_confirmed = False
        user.cognito_access_token = None
        user.cognito_refresh_token = None
        user.cognito_temp_password = None
        
        db.commit()
        print(f"✅ Cleared Cognito references for {email}")
        print(f"   User can now log in again via OAuth to create a new Cognito account")
        
    finally:
        db.close()

if __name__ == "__main__":
    print("=" * 60)
    print("Fix Deleted Cognito Users")
    print("=" * 60)
    
    if len(sys.argv) > 1:
        # Fix specific user
        email = sys.argv[1]
        print(f"\nFixing specific user: {email}")
        asyncio.run(fix_specific_user(email))
    else:
        # Check all users
        print("\nChecking all users...")
        asyncio.run(check_and_fix_deleted_users())