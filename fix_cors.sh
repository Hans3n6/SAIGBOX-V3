#!/bin/bash

echo "🔧 Fixing CORS configuration on EC2..."

# Configuration
INSTANCE_ID="i-0d394d6974a0e8021"
EC2_USER="ubuntu"
EC2_HOST="api.saigbox.com"

# Generate temporary SSH key
TEMP_KEY="/tmp/ec2-connect-cors-$$"
ssh-keygen -t rsa -f $TEMP_KEY -N "" -q

# Send public key to EC2
aws ec2-instance-connect send-ssh-public-key \
    --instance-id $INSTANCE_ID \
    --instance-os-user $EC2_USER \
    --ssh-public-key file://${TEMP_KEY}.pub \
    --availability-zone us-east-1c

echo "Updating nginx configuration to fix CORS..."
ssh -o StrictHostKeyChecking=no -i $TEMP_KEY $EC2_USER@$EC2_HOST << 'ENDSSH'
    # Update nginx configuration to fix duplicate CORS headers
    sudo tee /etc/nginx/sites-available/saigbox > /dev/null << 'EOF'
# HTTP to HTTPS redirect
server {
    listen 80;
    server_name api.saigbox.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS server
server {
    listen 443 ssl http2;
    server_name api.saigbox.com;

    # SSL certificates
    ssl_certificate /etc/letsencrypt/live/api.saigbox.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.saigbox.com/privkey.pem;
    
    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options SAMEORIGIN;
    add_header X-XSS-Protection "1; mode=block";
    
    # Main location block
    location / {
        # Handle OPTIONS preflight requests
        if ($request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' 'https://saigbox.com' always;
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
            add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization' always;
            add_header 'Access-Control-Allow-Credentials' 'true' always;
            add_header 'Access-Control-Max-Age' 1728000;
            add_header 'Content-Type' 'text/plain; charset=utf-8';
            add_header 'Content-Length' 0;
            return 204;
        }
        
        # Proxy to FastAPI
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Add CORS headers for actual requests (not OPTIONS)
        add_header 'Access-Control-Allow-Origin' 'https://saigbox.com' always;
        add_header 'Access-Control-Allow-Credentials' 'true' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range,Authorization' always;
    }
}
EOF
    
    # Test nginx configuration
    sudo nginx -t
    
    # Reload nginx
    sudo systemctl reload nginx
    
    echo "CORS configuration fixed!"
ENDSSH

# Also update FastAPI CORS middleware to be more specific
ssh -o StrictHostKeyChecking=no -i $TEMP_KEY $EC2_USER@$EC2_HOST << 'ENDSSH'
    # Check if main.py has wildcard CORS
    cd /home/ubuntu/SAIGBOX-V3
    
    # Backup original
    cp api/main.py api/main.py.backup
    
    # Update CORS configuration in FastAPI
    cat > /tmp/fix_cors.py << 'EOFPY'
import sys
import re

# Read the file
with open('api/main.py', 'r') as f:
    content = f.read()

# Find and replace CORS middleware configuration
# Look for allow_origins=["*"]
pattern = r'allow_origins=\["?\*"?\]'
replacement = 'allow_origins=["https://saigbox.com", "https://www.saigbox.com", "https://dashboard.saigbox.com", "http://localhost:3000"]'

content = re.sub(pattern, replacement, content)

# Also fix if it's using allow_origins=["*"] with quotes
pattern2 = r"allow_origins=\['?\*'?\]"
content = re.sub(pattern2, replacement, content)

# Write back
with open('api/main.py', 'w') as f:
    f.write(content)

print("CORS configuration updated in main.py")
EOFPY
    
    python3 /tmp/fix_cors.py
    
    # Restart FastAPI
    sudo systemctl restart saigbox
    
    echo "FastAPI restarted with updated CORS settings"
ENDSSH

# Clean up
rm -f $TEMP_KEY $TEMP_KEY.pub

echo "✅ CORS fix complete!"
echo ""
echo "Testing CORS headers..."
curl -s -I -X OPTIONS https://api.saigbox.com/api/auth/google/url \
    -H "Origin: https://saigbox.com" \
    -H "Access-Control-Request-Method: GET" | grep -i "access-control"