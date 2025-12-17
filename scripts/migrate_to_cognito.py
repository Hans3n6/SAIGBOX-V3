#!/usr/bin/env python3
"""
Migration script to move existing users to AWS Cognito and S3
This script will:
1. Create Cognito accounts for existing users
2. Migrate user data to S3
3. Update database with Cognito references
"""
import os
import sys
import asyncio
import random
import string
from datetime import datetime

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.database import User, Email, ActionItem
from core.cognito_auth import CognitoAuth
from core.user_storage import UserStorageService

# Initialize services
cognito_service = CognitoAuth()
storage_service = UserStorageService()

# Database setup
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./saigbox.db')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def generate_temp_password():
    """Generate a temporary password for migration"""
    return ''.join(random.choices(string.ascii_letters + string.digits + '!@#$%', k=12))

async def migrate_user(db_session, user, dry_run=False):
    """Migrate a single user to Cognito and S3"""
    print(f"\n{'[DRY RUN] ' if dry_run else ''}Migrating user: {user.email}")
    
    try:
        # Skip if already migrated
        if user.cognito_sub:
            print(f"  ✓ User already has Cognito ID: {user.cognito_sub}")
            
            # Still migrate data to S3 if not done
            if not dry_run:
                await migrate_user_data_to_s3(db_session, user)
            return True
        
        if not dry_run:
            # Generate temporary password
            temp_password = generate_temp_password()
            
            # Register user with Cognito
            result = await cognito_service.register_user(
                email=user.email,
                password=temp_password,
                full_name=user.name
            )
            
            if result['success']:
                # Update user record with Cognito sub
                user.cognito_sub = result['user_sub']
                user.cognito_temp_password = temp_password  # Store temporarily for email
                user.cognito_confirmed = False  # Will need email confirmation
                db_session.commit()
                
                print(f"  ✓ Created Cognito account with ID: {result['user_sub']}")
                print(f"  ✓ Temporary password: {temp_password}")
                print(f"  ⚠ User will need to confirm email and reset password")
                
                # Migrate user data to S3
                await migrate_user_data_to_s3(db_session, user)
                
                return True
            else:
                print(f"  ✗ Failed to create Cognito account: {result['error']}")
                return False
        else:
            print(f"  → Would create Cognito account")
            print(f"  → Would migrate data to S3")
            return True
            
    except Exception as e:
        print(f"  ✗ Error migrating user: {str(e)}")
        return False

async def migrate_user_data_to_s3(db_session, user):
    """Migrate user's data to S3"""
    if not user.cognito_sub:
        print(f"  ⚠ No Cognito ID for user, skipping S3 migration")
        return
    
    try:
        # Save user profile
        profile_data = {
            'id': str(user.id),
            'email': user.email,
            'name': user.name,
            'created_at': user.created_at.isoformat() if user.created_at else None,
            'last_login': user.last_login.isoformat() if user.last_login else None,
            'migrated_at': datetime.utcnow().isoformat()
        }
        
        await storage_service.save_user_profile(user.cognito_sub, profile_data)
        print(f"  ✓ Migrated user profile to S3")
        
        # Migrate emails in batches
        emails = db_session.query(Email).filter(
            Email.user_id == user.id,
            Email.deleted_at.is_(None)
        ).all()
        
        if emails:
            email_batch = []
            for email in emails:
                email_data = {
                    'id': str(email.id),
                    'subject': email.subject,
                    'sender': email.sender,
                    'sender_name': email.sender_name,
                    'received_at': email.received_at.isoformat() if email.received_at else None,
                    'body': email.body,
                    'snippet': email.snippet,
                    'is_read': email.is_read,
                    'is_important': email.is_important,
                    'urgency_score': email.urgency_score
                }
                email_batch.append(email_data)
                
                # Save in batches of 100
                if len(email_batch) >= 100:
                    batch_id = f"migration_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
                    await storage_service.save_user_emails(user.cognito_sub, email_batch, batch_id)
                    email_batch = []
            
            # Save remaining emails
            if email_batch:
                batch_id = f"migration_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
                await storage_service.save_user_emails(user.cognito_sub, email_batch, batch_id)
            
            print(f"  ✓ Migrated {len(emails)} emails to S3")
        
        # Migrate action items
        action_items = db_session.query(ActionItem).filter(
            ActionItem.user_id == user.id
        ).all()
        
        if action_items:
            # Save as part of user settings
            settings = await storage_service.get_user_settings(user.cognito_sub) or {}
            settings['action_items'] = [
                {
                    'id': str(item.id),
                    'title': item.title,
                    'description': item.description,
                    'priority': item.priority,
                    'due_date': item.due_date.isoformat() if item.due_date else None,
                    'completed': item.completed,
                    'created_at': item.created_at.isoformat() if item.created_at else None
                }
                for item in action_items
            ]
            await storage_service.save_user_settings(user.cognito_sub, settings)
            print(f"  ✓ Migrated {len(action_items)} action items to S3")
        
    except Exception as e:
        print(f"  ✗ Error migrating data to S3: {str(e)}")

async def main():
    """Main migration function"""
    print("=" * 60)
    print("SAIGBOX User Migration to AWS Cognito and S3")
    print("=" * 60)
    
    # Parse arguments
    dry_run = '--dry-run' in sys.argv
    
    if dry_run:
        print("\n🔍 DRY RUN MODE - No changes will be made")
    else:
        print("\n⚠️  PRODUCTION MODE - Changes will be committed")
        response = input("\nAre you sure you want to continue? (yes/no): ")
        if response.lower() != 'yes':
            print("Migration cancelled")
            return
    
    # Create database session
    db = SessionLocal()
    
    try:
        # Get all users
        users = db.query(User).all()
        total_users = len(users)
        
        print(f"\nFound {total_users} users to process")
        
        # Track results
        successful = 0
        failed = 0
        skipped = 0
        
        # Migrate each user
        for i, user in enumerate(users, 1):
            print(f"\n[{i}/{total_users}]", end="")
            
            if user.cognito_sub and not dry_run:
                # User already has Cognito ID, just ensure data is in S3
                await migrate_user_data_to_s3(db, user)
                skipped += 1
            else:
                success = await migrate_user(db, user, dry_run)
                if success:
                    successful += 1
                else:
                    failed += 1
        
        # Print summary
        print("\n" + "=" * 60)
        print("Migration Summary")
        print("=" * 60)
        print(f"Total users: {total_users}")
        print(f"✓ Successful: {successful}")
        print(f"⚠ Skipped (already migrated): {skipped}")
        print(f"✗ Failed: {failed}")
        
        if not dry_run and successful > 0:
            print("\n📧 Next Steps:")
            print("1. Send password reset emails to migrated users")
            print("2. Users will need to:")
            print("   - Confirm their email address")
            print("   - Reset their password")
            print("   - Log in with new Cognito credentials")
            
            # Generate CSV report
            report_file = f"migration_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            with open(report_file, 'w') as f:
                f.write("Email,Cognito ID,Temp Password,Status\n")
                for user in users:
                    status = "Migrated" if user.cognito_sub else "Failed"
                    temp_pwd = getattr(user, 'cognito_temp_password', 'N/A')
                    f.write(f"{user.email},{user.cognito_sub or 'N/A'},{temp_pwd},{status}\n")
            
            print(f"\n📄 Migration report saved to: {report_file}")
        
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(main())