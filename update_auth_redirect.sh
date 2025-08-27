#!/bin/bash

echo "🔄 Updating OAuth redirect to dashboard..."

# Configuration
INSTANCE_ID="i-0d394d6974a0e8021"
EC2_USER="ubuntu"
EC2_HOST="api.saigbox.com"

# Generate temporary SSH key
TEMP_KEY="/tmp/ec2-connect-redirect-$$"
ssh-keygen -t rsa -f $TEMP_KEY -N "" -q

# Send public key to EC2
aws ec2-instance-connect send-ssh-public-key \
    --instance-id $INSTANCE_ID \
    --instance-os-user $EC2_USER \
    --ssh-public-key file://${TEMP_KEY}.pub \
    --availability-zone us-east-1c

echo "Updating OAuth callback redirects..."
ssh -o StrictHostKeyChecking=no -i $TEMP_KEY $EC2_USER@$EC2_HOST << 'ENDSSH'
    cd /home/ubuntu/SAIGBOX-V3
    
    # Backup the original file
    cp api/main.py api/main.py.backup-redirect
    
    # Create Python script to update redirects
    cat > /tmp/update_redirects.py << 'EOFPY'
import re

with open('api/main.py', 'r') as f:
    lines = f.readlines()

# Dashboard URL
DASHBOARD_URL = "https://dashboard.saigbox.com"

# Update the file
for i in range(len(lines)):
    # Fix Google callback redirect
    if 'async def google_auth_callback' in lines[i]:
        # Find the redirect line within this function
        j = i
        while j < len(lines) and 'def ' not in lines[j] or j == i:
            if 'RedirectResponse(url="/"' in lines[j]:
                lines[j] = lines[j].replace('url="/"', f'url="{DASHBOARD_URL}"')
                print(f"Updated Google callback redirect at line {j+1}")
            # Also update secure cookie setting for production
            if 'secure=False' in lines[j] and 'Set to True in production' in lines[j]:
                lines[j] = lines[j].replace('secure=False', 'secure=True')
                print(f"Updated secure cookie setting at line {j+1}")
            j += 1
    
    # Fix Microsoft callback redirect
    if 'async def microsoft_auth_callback' in lines[i]:
        # Find the redirect line within this function
        j = i
        while j < len(lines) and 'def ' not in lines[j] or j == i:
            if 'RedirectResponse(url="/"' in lines[j]:
                lines[j] = lines[j].replace('url="/"', f'url="{DASHBOARD_URL}"')
                print(f"Updated Microsoft callback redirect at line {j+1}")
            # Also update secure cookie setting
            if 'secure=False' in lines[j]:
                lines[j] = lines[j].replace('secure=False', 'secure=True')
                print(f"Updated secure cookie setting at line {j+1}")
            j += 1
    
    # Fix error redirects to use full URL
    if 'RedirectResponse(url=f"/login' in lines[i]:
        lines[i] = lines[i].replace('url=f"/login', 'url=f"https://saigbox.com/login')
        print(f"Updated error redirect at line {i+1}")
    
    # Fix any remaining secure=False for cookies
    if 'secure=False' in lines[i] and 'cookie' in lines[i].lower():
        lines[i] = lines[i].replace('secure=False', 'secure=True')
        print(f"Updated cookie security at line {i+1}")

# Write the updated file
with open('api/main.py', 'w') as f:
    f.writelines(lines)

print("\nRedirect URLs updated successfully!")
print(f"OAuth callbacks will now redirect to: {DASHBOARD_URL}")
EOFPY
    
    # Run the update script
    python3 /tmp/update_redirects.py
    
    # Show the changes
    echo -e "\nUpdated redirects:"
    grep -n "RedirectResponse" api/main.py | grep -E "dashboard|saigbox" | head -5
    
    # Also update the auth.py file if needed
    cat > /tmp/update_auth.py << 'EOFPY'
import os

# Update environment variables if needed
env_file = '.env'
if os.path.exists(env_file):
    with open(env_file, 'r') as f:
        lines = f.readlines()
    
    updated = False
    for i in range(len(lines)):
        # Add dashboard URL if not present
        if 'DASHBOARD_URL' not in ''.join(lines):
            lines.append('\n# Dashboard URL\n')
            lines.append('DASHBOARD_URL=https://dashboard.saigbox.com\n')
            updated = True
            break
    
    if updated:
        with open(env_file, 'w') as f:
            f.writelines(lines)
        print(".env file updated with DASHBOARD_URL")
EOFPY
    
    python3 /tmp/update_auth.py
    
    # Restart FastAPI
    echo "Restarting FastAPI with updated configuration..."
    sudo systemctl restart saigbox
    sleep 3
    
    echo "✅ OAuth redirect updates complete!"
ENDSSH

# Clean up
rm -f $TEMP_KEY $TEMP_KEY.pub

echo ""
echo "✅ OAuth callbacks updated!"
echo ""
echo "Changes made:"
echo "1. OAuth callbacks now redirect to: https://dashboard.saigbox.com"
echo "2. Cookies set with secure=True for HTTPS"
echo "3. Error redirects use full URLs"
echo ""
echo "Test the flow:"
echo "1. Go to https://saigbox.com/login"
echo "2. Click 'Continue with Google'"
echo "3. After auth, you'll be redirected to https://dashboard.saigbox.com"