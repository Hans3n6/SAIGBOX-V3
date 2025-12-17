"""
User Data Storage Service for S3
Manages user-specific data storage in S3 with proper isolation
"""
import os
import json
import boto3
from typing import Dict, Any, Optional, List
from datetime import datetime
from botocore.exceptions import ClientError
import hashlib
import io

class UserStorageService:
    """S3-based storage service for user data"""
    
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            region_name=os.getenv('AWS_REGION', 'us-east-1'),
            aws_access_key_id=os.getenv('AWS_STORAGE_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_STORAGE_SECRET_ACCESS_KEY')
        )
        
        # Determine bucket based on environment
        self.environment = os.getenv('ENVIRONMENT', 'development')
        if self.environment == 'production':
            self.bucket_name = os.getenv('S3_BUCKET_PRODUCTION', 'saigbox-user-data-prod')
        else:
            self.bucket_name = os.getenv('S3_BUCKET_DEVELOPMENT', 'saigbox-user-data-dev')
    
    def _get_user_prefix(self, user_id: str) -> str:
        """Generate S3 prefix for user data isolation"""
        # Use hash to avoid exposing user IDs directly
        user_hash = hashlib.sha256(user_id.encode()).hexdigest()[:16]
        return f"users/{user_hash}/{user_id}"
    
    async def save_user_profile(self, user_id: str, profile_data: Dict[str, Any]) -> bool:
        """Save user profile data to S3"""
        try:
            key = f"{self._get_user_prefix(user_id)}/profile.json"
            
            # Add metadata
            profile_data['last_updated'] = datetime.utcnow().isoformat()
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=json.dumps(profile_data),
                ContentType='application/json',
                ServerSideEncryption='AES256',
                Metadata={
                    'user_id': user_id,
                    'data_type': 'profile'
                }
            )
            
            return True
            
        except ClientError as e:
            print(f"Error saving user profile: {e}")
            return False
    
    async def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve user profile data from S3"""
        try:
            key = f"{self._get_user_prefix(user_id)}/profile.json"
            
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=key
            )
            
            profile_data = json.loads(response['Body'].read().decode('utf-8'))
            return profile_data
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return None
            print(f"Error retrieving user profile: {e}")
            return None
    
    async def save_user_emails(self, user_id: str, emails: List[Dict[str, Any]], batch_id: str = None) -> bool:
        """Save user email data to S3"""
        try:
            if not batch_id:
                batch_id = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            
            key = f"{self._get_user_prefix(user_id)}/emails/{batch_id}.json"
            
            email_data = {
                'user_id': user_id,
                'batch_id': batch_id,
                'timestamp': datetime.utcnow().isoformat(),
                'count': len(emails),
                'emails': emails
            }
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=json.dumps(email_data),
                ContentType='application/json',
                ServerSideEncryption='AES256',
                Metadata={
                    'user_id': user_id,
                    'data_type': 'emails',
                    'email_count': str(len(emails))
                }
            )
            
            return True
            
        except ClientError as e:
            print(f"Error saving user emails: {e}")
            return False
    
    async def get_user_emails(self, user_id: str, limit: int = None) -> List[Dict[str, Any]]:
        """Retrieve user email data from S3"""
        try:
            prefix = f"{self._get_user_prefix(user_id)}/emails/"
            
            # List all email batches for the user
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            all_emails = []
            
            if 'Contents' in response:
                # Sort by last modified to get most recent first
                objects = sorted(response['Contents'], key=lambda x: x['LastModified'], reverse=True)
                
                for obj in objects:
                    if limit and len(all_emails) >= limit:
                        break
                    
                    # Get the email batch
                    email_response = self.s3_client.get_object(
                        Bucket=self.bucket_name,
                        Key=obj['Key']
                    )
                    
                    email_data = json.loads(email_response['Body'].read().decode('utf-8'))
                    all_emails.extend(email_data.get('emails', []))
                    
                    if limit and len(all_emails) > limit:
                        all_emails = all_emails[:limit]
            
            return all_emails
            
        except ClientError as e:
            print(f"Error retrieving user emails: {e}")
            return []
    
    async def save_user_settings(self, user_id: str, settings: Dict[str, Any]) -> bool:
        """Save user settings/preferences to S3"""
        try:
            key = f"{self._get_user_prefix(user_id)}/settings.json"
            
            settings['last_updated'] = datetime.utcnow().isoformat()
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=json.dumps(settings),
                ContentType='application/json',
                ServerSideEncryption='AES256',
                Metadata={
                    'user_id': user_id,
                    'data_type': 'settings'
                }
            )
            
            return True
            
        except ClientError as e:
            print(f"Error saving user settings: {e}")
            return False
    
    async def get_user_settings(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve user settings from S3"""
        try:
            key = f"{self._get_user_prefix(user_id)}/settings.json"
            
            response = self.s3_client.get_object(
                Bucket=self.bucket_name,
                Key=key
            )
            
            settings = json.loads(response['Body'].read().decode('utf-8'))
            return settings
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return {}  # Return empty settings if none exist
            print(f"Error retrieving user settings: {e}")
            return None
    
    async def save_user_attachment(self, user_id: str, email_id: str, attachment_name: str, 
                                  attachment_data: bytes, content_type: str = 'application/octet-stream') -> Optional[str]:
        """Save email attachment to S3 and return URL"""
        try:
            # Sanitize filename
            safe_name = "".join(c for c in attachment_name if c.isalnum() or c in ('_', '-', '.'))
            key = f"{self._get_user_prefix(user_id)}/attachments/{email_id}/{safe_name}"
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=attachment_data,
                ContentType=content_type,
                ServerSideEncryption='AES256',
                Metadata={
                    'user_id': user_id,
                    'email_id': email_id,
                    'original_name': attachment_name
                }
            )
            
            # Generate presigned URL for access (valid for 7 days)
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': key},
                ExpiresIn=604800  # 7 days
            )
            
            return url
            
        except ClientError as e:
            print(f"Error saving attachment: {e}")
            return None
    
    async def get_user_storage_usage(self, user_id: str) -> Dict[str, Any]:
        """Get storage usage statistics for a user"""
        try:
            prefix = self._get_user_prefix(user_id)
            
            # List all objects for the user
            paginator = self.s3_client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix=prefix)
            
            total_size = 0
            total_objects = 0
            file_types = {}
            
            for page in pages:
                if 'Contents' in page:
                    for obj in page['Contents']:
                        total_size += obj['Size']
                        total_objects += 1
                        
                        # Categorize by type
                        if '/emails/' in obj['Key']:
                            file_types['emails'] = file_types.get('emails', 0) + 1
                        elif '/attachments/' in obj['Key']:
                            file_types['attachments'] = file_types.get('attachments', 0) + 1
                        elif '/profile.json' in obj['Key']:
                            file_types['profile'] = 1
                        elif '/settings.json' in obj['Key']:
                            file_types['settings'] = 1
            
            return {
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'total_objects': total_objects,
                'file_types': file_types
            }
            
        except ClientError as e:
            print(f"Error getting storage usage: {e}")
            return {
                'total_size_bytes': 0,
                'total_size_mb': 0,
                'total_objects': 0,
                'file_types': {}
            }
    
    async def delete_user_data(self, user_id: str) -> bool:
        """Delete all user data from S3 (for GDPR compliance)"""
        try:
            prefix = self._get_user_prefix(user_id)
            
            # List all objects for the user
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            
            if 'Contents' in response:
                # Delete all objects
                objects = [{'Key': obj['Key']} for obj in response['Contents']]
                
                self.s3_client.delete_objects(
                    Bucket=self.bucket_name,
                    Delete={'Objects': objects}
                )
            
            return True
            
        except ClientError as e:
            print(f"Error deleting user data: {e}")
            return False
    
    async def backup_user_data(self, user_id: str) -> Optional[str]:
        """Create a backup archive of all user data"""
        try:
            import zipfile
            from io import BytesIO
            
            prefix = self._get_user_prefix(user_id)
            
            # Create in-memory zip file
            zip_buffer = BytesIO()
            
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                # List all objects for the user
                response = self.s3_client.list_objects_v2(
                    Bucket=self.bucket_name,
                    Prefix=prefix
                )
                
                if 'Contents' in response:
                    for obj in response['Contents']:
                        # Get object
                        obj_response = self.s3_client.get_object(
                            Bucket=self.bucket_name,
                            Key=obj['Key']
                        )
                        
                        # Add to zip
                        file_name = obj['Key'].replace(prefix + '/', '')
                        zip_file.writestr(file_name, obj_response['Body'].read())
            
            # Save backup to S3
            backup_key = f"{prefix}/backups/backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
            
            zip_buffer.seek(0)
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=backup_key,
                Body=zip_buffer.getvalue(),
                ContentType='application/zip',
                ServerSideEncryption='AES256'
            )
            
            # Generate download URL
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': backup_key},
                ExpiresIn=86400  # 24 hours
            )
            
            return url
            
        except ClientError as e:
            print(f"Error creating backup: {e}")
            return None