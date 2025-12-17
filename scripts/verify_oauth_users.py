#!/usr/bin/env python3
"""
Script to mark OAuth users' emails as verified in Cognito
This fixes the issue where OAuth users show as unverified
"""
import os
import sys
import boto3
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.database import User

# Initialize Cognito client
cognito_client = boto3.client(
    'cognito-idp',
    region_name=os.getenv('AWS_REGION', 'us-east-1'),
    aws_access_key_id=os.getenv('AWS_STORAGE_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_STORAGE_SECRET_ACCESS_KEY')
)

user_pool_id = os.getenv('AWS_COGNITO_USER_POOL_ID')

# Database setup
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./saigbox.db')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def verify_oauth_users():
    """Mark all OAuth users as verified in Cognito"""
    db = SessionLocal()
    
    try:
        # Get all users with Cognito IDs who logged in via OAuth
        oauth_users = db.query(User).filter(
            User.cognito_sub.isnot(None),
            User.provider.in_(['google', 'microsoft'])
        ).all()
        
        print(f"Found {len(oauth_users)} OAuth users with Cognito accounts")
        
        verified_count = 0
        for user in oauth_users:
            try:
                # Mark email as verified in Cognito
                cognito_client.admin_update_user_attributes(
                    UserPoolId=user_pool_id,
                    Username=user.email,
                    UserAttributes=[
                        {'Name': 'email_verified', 'Value': 'true'}
                    ]
                )
                
                # Also confirm the user if not already confirmed
                try:
                    cognito_client.admin_confirm_sign_up(
                        UserPoolId=user_pool_id,
                        Username=user.email
                    )
                except:
                    pass  # User might already be confirmed
                
                # Update local database
                user.cognito_confirmed = True
                db.commit()
                
                print(f"✅ Verified: {user.email}")
                verified_count += 1
                
            except Exception as e:
                print(f"❌ Failed to verify {user.email}: {e}")
        
        print(f"\n✅ Successfully verified {verified_count} users")
        
    finally:
        db.close()

if __name__ == "__main__":
    print("=" * 60)
    print("Verifying OAuth Users in Cognito")
    print("=" * 60)
    verify_oauth_users()