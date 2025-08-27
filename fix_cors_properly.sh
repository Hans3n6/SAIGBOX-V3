#!/bin/bash

echo "🔧 Fixing CORS - removing duplicate headers..."

# Configuration
INSTANCE_ID="i-0d394d6974a0e8021"
EC2_USER="ubuntu"
EC2_HOST="api.saigbox.com"

# Generate temporary SSH key
TEMP_KEY="/tmp/ec2-connect-cors-fix-$$"
ssh-keygen -t rsa -f $TEMP_KEY -N "" -q

# Send public key to EC2
aws ec2-instance-connect send-ssh-public-key \
    --instance-id $INSTANCE_ID \
    --instance-os-user $EC2_USER \
    --ssh-public-key file://${TEMP_KEY}.pub \
    --availability-zone us-east-1c

echo "Updating nginx to NOT add CORS headers (let FastAPI handle it)..."
ssh -o StrictHostKeyChecking=no -i $TEMP_KEY $EC2_USER@$EC2_HOST << 'ENDSSH'
    # Update nginx configuration - remove ALL CORS headers (FastAPI will handle them)
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
    
    # Security headers (but NOT CORS headers)
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Frame-Options SAMEORIGIN always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Main location block - NO CORS headers here!
    location / {
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
        
        # DO NOT add any CORS headers here - FastAPI handles them
    }
}
EOF
    
    # Test nginx configuration
    sudo nginx -t
    
    # Reload nginx
    sudo systemctl reload nginx
    
    echo "Nginx updated - CORS headers removed from nginx"
ENDSSH

# Make sure FastAPI is properly configured for CORS
ssh -o StrictHostKeyChecking=no -i $TEMP_KEY $EC2_USER@$EC2_HOST << 'ENDSSH'
    cd /home/ubuntu/SAIGBOX-V3
    
    # Check current main.py CORS setup
    echo "Current CORS configuration in FastAPI:"
    grep -A5 "CORSMiddleware" api/main.py || echo "No CORSMiddleware found"
    
    # Ensure proper CORS middleware setup
    cat > /tmp/ensure_cors.py << 'EOFPY'
import re

with open('api/main.py', 'r') as f:
    content = f.read()

# Check if CORSMiddleware is properly configured
if 'CORSMiddleware' not in content:
    print("ERROR: CORSMiddleware not found in main.py")
    # Add it after the app creation
    import_line = "from fastapi.middleware.cors import CORSMiddleware\n"
    if import_line not in content:
        # Add import at the top with other imports
        content = content.replace("from fastapi import FastAPI", "from fastapi import FastAPI\nfrom fastapi.middleware.cors import CORSMiddleware")
    
    # Add middleware after app creation
    app_creation = "app = FastAPI("
    if app_creation in content:
        # Find the end of app creation
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if app_creation in line:
                # Find the closing parenthesis
                j = i
                while j < len(lines) and ')' not in lines[j]:
                    j += 1
                # Insert CORS middleware after app creation
                cors_config = '''
# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://saigbox.com",
        "https://www.saigbox.com", 
        "https://dashboard.saigbox.com",
        "http://localhost:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
'''
                lines.insert(j + 1, cors_config)
                content = '\n'.join(lines)
                break

with open('api/main.py', 'w') as f:
    f.write(content)

print("CORS middleware configuration verified/updated")
EOFPY
    
    python3 /tmp/ensure_cors.py
    
    # Show the CORS config
    echo "Updated CORS configuration:"
    grep -A7 "CORSMiddleware" api/main.py
    
    # Restart FastAPI
    sudo systemctl restart saigbox
    sleep 3
    
    echo "FastAPI restarted with proper CORS configuration"
ENDSSH

# Clean up
rm -f $TEMP_KEY $TEMP_KEY.pub

echo "✅ CORS configuration fixed!"
echo ""
echo "Testing CORS headers (should only show once)..."
curl -s -I https://api.saigbox.com/api/auth/google/url \
    -H "Origin: https://saigbox.com" | grep -i "access-control-allow-origin"

echo ""
echo "Testing API functionality..."
curl -s https://api.saigbox.com/api/auth/google/url \
    -H "Origin: https://saigbox.com" | python3 -c "import sys, json; d=json.load(sys.stdin); print('✅ API responding correctly' if 'url' in d else '❌ API error')"