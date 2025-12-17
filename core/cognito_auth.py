"""
AWS Cognito Authentication Service
Handles user authentication, registration, and token management
"""
import os
import hmac
import hashlib
import base64
import json
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import boto3
from botocore.exceptions import ClientError
from jose import jwt, JWTError
from passlib.hash import bcrypt

class CognitoAuth:
    """AWS Cognito authentication service"""
    
    def __init__(self):
        self.client = boto3.client(
            'cognito-idp',
            region_name=os.getenv('AWS_REGION', 'us-east-1'),
            aws_access_key_id=os.getenv('AWS_STORAGE_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_STORAGE_SECRET_ACCESS_KEY')
        )
        self.user_pool_id = os.getenv('AWS_COGNITO_USER_POOL_ID')
        self.client_id = os.getenv('AWS_COGNITO_CLIENT_ID')
        self.client_secret = os.getenv('AWS_COGNITO_CLIENT_SECRET')
        self.region = os.getenv('AWS_REGION', 'us-east-1')
        
    def _get_secret_hash(self, username: str) -> str:
        """Generate secret hash for Cognito API calls"""
        message = bytes(username + self.client_id, 'utf-8')
        secret = bytes(self.client_secret, 'utf-8')
        dig = hmac.new(secret, message, hashlib.sha256).digest()
        return base64.b64encode(dig).decode()
    
    async def register_user(self, email: str, password: str, full_name: str = None, auto_verify: bool = False) -> Dict[str, Any]:
        """Register a new user in Cognito"""
        try:
            user_attributes = [
                {'Name': 'email', 'Value': email}
            ]
            
            if full_name:
                user_attributes.append({'Name': 'name', 'Value': full_name})
            
            response = self.client.sign_up(
                ClientId=self.client_id,
                SecretHash=self._get_secret_hash(email),
                Username=email,
                Password=password,
                UserAttributes=user_attributes
            )
            
            # Auto-verify email for OAuth users
            if auto_verify and response.get('UserSub'):
                try:
                    self.client.admin_confirm_sign_up(
                        UserPoolId=self.user_pool_id,
                        Username=email
                    )
                    
                    # Also mark email as verified
                    self.client.admin_update_user_attributes(
                        UserPoolId=self.user_pool_id,
                        Username=email,
                        UserAttributes=[
                            {'Name': 'email_verified', 'Value': 'true'}
                        ]
                    )
                    print(f"✅ Auto-verified email for OAuth user: {email}")
                except Exception as e:
                    print(f"Warning: Could not auto-verify user: {e}")
            
            return {
                'success': True,
                'user_sub': response['UserSub'],
                'confirmation_required': not response.get('UserConfirmed', False),
                'message': 'User registered successfully'
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            if error_code == 'UsernameExistsException':
                return {'success': False, 'error': 'User already exists'}
            elif error_code == 'InvalidPasswordException':
                return {'success': False, 'error': 'Password does not meet requirements'}
            else:
                return {'success': False, 'error': error_message}
    
    async def confirm_registration(self, email: str, confirmation_code: str) -> Dict[str, Any]:
        """Confirm user registration with verification code"""
        try:
            self.client.confirm_sign_up(
                ClientId=self.client_id,
                SecretHash=self._get_secret_hash(email),
                Username=email,
                ConfirmationCode=confirmation_code
            )
            
            return {'success': True, 'message': 'Email confirmed successfully'}
            
        except ClientError as e:
            error_message = e.response['Error']['Message']
            return {'success': False, 'error': error_message}
    
    async def authenticate_user(self, email: str, password: str) -> Dict[str, Any]:
        """Authenticate user and return tokens"""
        try:
            response = self.client.initiate_auth(
                ClientId=self.client_id,
                AuthFlow='USER_SRP_AUTH',
                AuthParameters={
                    'USERNAME': email,
                    'PASSWORD': password,
                    'SECRET_HASH': self._get_secret_hash(email)
                }
            )
            
            # For SRP auth, we need to respond to the challenge
            if response.get('ChallengeName') == 'PASSWORD_VERIFIER':
                # This is simplified - full SRP implementation would be more complex
                response = self.client.admin_initiate_auth(
                    UserPoolId=self.user_pool_id,
                    ClientId=self.client_id,
                    AuthFlow='ADMIN_NO_SRP_AUTH',
                    AuthParameters={
                        'USERNAME': email,
                        'PASSWORD': password,
                        'SECRET_HASH': self._get_secret_hash(email)
                    }
                )
            
            if 'AuthenticationResult' in response:
                result = response['AuthenticationResult']
                return {
                    'success': True,
                    'access_token': result['AccessToken'],
                    'id_token': result['IdToken'],
                    'refresh_token': result['RefreshToken'],
                    'expires_in': result['ExpiresIn']
                }
            else:
                return {'success': False, 'error': 'Authentication failed'}
                
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            if error_code == 'NotAuthorizedException':
                return {'success': False, 'error': 'Invalid email or password'}
            elif error_code == 'UserNotConfirmedException':
                return {'success': False, 'error': 'Email not confirmed', 'confirmation_required': True}
            else:
                return {'success': False, 'error': error_message}
    
    async def refresh_token(self, refresh_token: str, email: str) -> Dict[str, Any]:
        """Refresh access token using refresh token"""
        try:
            response = self.client.initiate_auth(
                ClientId=self.client_id,
                AuthFlow='REFRESH_TOKEN_AUTH',
                AuthParameters={
                    'REFRESH_TOKEN': refresh_token,
                    'SECRET_HASH': self._get_secret_hash(email)
                }
            )
            
            if 'AuthenticationResult' in response:
                result = response['AuthenticationResult']
                return {
                    'success': True,
                    'access_token': result['AccessToken'],
                    'id_token': result['IdToken'],
                    'expires_in': result['ExpiresIn']
                }
            else:
                return {'success': False, 'error': 'Token refresh failed'}
                
        except ClientError as e:
            error_message = e.response['Error']['Message']
            return {'success': False, 'error': error_message}
    
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user information from access token"""
        try:
            response = self.client.get_user(AccessToken=access_token)
            
            user_info = {
                'username': response['Username'],
                'attributes': {}
            }
            
            for attr in response['UserAttributes']:
                user_info['attributes'][attr['Name']] = attr['Value']
            
            return {
                'success': True,
                'user': user_info
            }
            
        except ClientError as e:
            error_message = e.response['Error']['Message']
            return {'success': False, 'error': error_message}
    
    async def get_user_info_by_sub(self, user_sub: str) -> Optional[Dict[str, Any]]:
        """Check if a user exists in Cognito by their sub (user ID)"""
        try:
            # List users with the given sub
            response = self.client.list_users(
                UserPoolId=self.user_pool_id,
                Filter=f'sub = "{user_sub}"',
                Limit=1
            )
            
            if response.get('Users'):
                user = response['Users'][0]
                return {
                    'username': user['Username'],
                    'status': user['UserStatus'],
                    'enabled': user['Enabled']
                }
            return None
            
        except ClientError:
            return None
    
    async def change_password(self, access_token: str, old_password: str, new_password: str) -> Dict[str, Any]:
        """Change user password"""
        try:
            self.client.change_password(
                AccessToken=access_token,
                PreviousPassword=old_password,
                ProposedPassword=new_password
            )
            
            return {'success': True, 'message': 'Password changed successfully'}
            
        except ClientError as e:
            error_message = e.response['Error']['Message']
            return {'success': False, 'error': error_message}
    
    async def forgot_password(self, email: str) -> Dict[str, Any]:
        """Initiate forgot password flow"""
        try:
            self.client.forgot_password(
                ClientId=self.client_id,
                SecretHash=self._get_secret_hash(email),
                Username=email
            )
            
            return {'success': True, 'message': 'Password reset code sent to email'}
            
        except ClientError as e:
            error_message = e.response['Error']['Message']
            return {'success': False, 'error': error_message}
    
    async def reset_password(self, email: str, confirmation_code: str, new_password: str) -> Dict[str, Any]:
        """Reset password with confirmation code"""
        try:
            self.client.confirm_forgot_password(
                ClientId=self.client_id,
                SecretHash=self._get_secret_hash(email),
                Username=email,
                ConfirmationCode=confirmation_code,
                Password=new_password
            )
            
            return {'success': True, 'message': 'Password reset successfully'}
            
        except ClientError as e:
            error_message = e.response['Error']['Message']
            return {'success': False, 'error': error_message}
    
    async def sign_out(self, access_token: str) -> Dict[str, Any]:
        """Sign out user (invalidate tokens)"""
        try:
            self.client.global_sign_out(AccessToken=access_token)
            return {'success': True, 'message': 'User signed out successfully'}
            
        except ClientError as e:
            error_message = e.response['Error']['Message']
            return {'success': False, 'error': error_message}
    
    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode JWT token"""
        try:
            # Get the JWT key set from Cognito
            jwks_url = f'https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}/.well-known/jwks.json'
            
            # In production, cache this
            import requests
            response = requests.get(jwks_url)
            keys = response.json()['keys']
            
            # Get the key id from the token header
            headers = jwt.get_unverified_headers(token)
            kid = headers['kid']
            
            # Find the key
            key = next((k for k in keys if k['kid'] == kid), None)
            if not key:
                return None
            
            # Decode the token
            decoded = jwt.decode(
                token,
                key,
                algorithms=['RS256'],
                audience=self.client_id,
                options={"verify_at_hash": False}
            )
            
            return decoded
            
        except (JWTError, Exception):
            return None