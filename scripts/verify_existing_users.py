#!/usr/bin/env python3
"""
Script to verify existing unverified users in Cognito
Requires admin permissions - run this after adding IAM permissions
"""
import os
import sys
import boto3
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

# Initialize Cognito client
cognito_client = boto3.client(
    'cognito-idp',
    region_name=os.getenv('AWS_REGION', 'us-east-1'),
    aws_access_key_id=os.getenv('AWS_STORAGE_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_STORAGE_SECRET_ACCESS_KEY')
)

user_pool_id = os.getenv('AWS_COGNITO_USER_POOL_ID')

def verify_existing_users():
    """Verify all existing unverified users"""
    try:
        # List all users
        response = cognito_client.list_users(
            UserPoolId=user_pool_id,
            Limit=60
        )
        
        users = response.get('Users', [])
        print(f"Found {len(users)} users in Cognito")
        
        unverified_count = 0
        verified_count = 0
        
        for user in users:
            username = user['Username']
            attributes = {attr['Name']: attr['Value'] for attr in user.get('Attributes', [])}
            email = attributes.get('email', 'N/A')
            email_verified = attributes.get('email_verified', 'false')
            
            if email_verified == 'false':
                print(f"❌ Unverified: {email} ({username})")
                unverified_count += 1
                
                # Try to verify the user
                try:
                    # First try to confirm the user
                    try:
                        cognito_client.admin_confirm_sign_up(
                            UserPoolId=user_pool_id,
                            Username=username
                        )
                        print(f"   ✅ Confirmed user signup")
                    except:
                        pass  # User might already be confirmed
                    
                    # Update email_verified attribute
                    cognito_client.admin_update_user_attributes(
                        UserPoolId=user_pool_id,
                        Username=username,
                        UserAttributes=[
                            {'Name': 'email_verified', 'Value': 'true'}
                        ]
                    )
                    print(f"   ✅ Verified email for {email}")
                    verified_count += 1
                    
                except Exception as e:
                    print(f"   ❌ Failed to verify: {e}")
            else:
                print(f"✅ Already verified: {email}")
        
        print(f"\nSummary:")
        print(f"  Total users: {len(users)}")
        print(f"  Unverified found: {unverified_count}")
        print(f"  Successfully verified: {verified_count}")
        
        if verified_count < unverified_count:
            print(f"\n⚠️  Some users could not be verified.")
            print("You may need to add the IAM permissions from aws/cognito_iam_policy.json")
        
    except Exception as e:
        print(f"Error: {e}")
        if "AccessDeniedException" in str(e):
            print("\n❌ Access Denied - Add IAM permissions first:")
            print("   1. Go to AWS IAM Console")
            print("   2. Find user: saigbox-storage-user")
            print("   3. Add inline policy from aws/cognito_iam_policy.json")

if __name__ == "__main__":
    print("=" * 60)
    print("Verifying Existing Cognito Users")
    print("=" * 60)
    verify_existing_users()