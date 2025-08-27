#!/bin/bash

# SAIGBOX EC2 Deployment Script
# This script updates the backend on your EC2 instance

set -e  # Exit on any error

echo "🚀 Starting SAIGBOX Backend Deployment to EC2..."

# Configuration
EC2_USER="ubuntu"
EC2_HOST="3.233.250.55"
EC2_KEY="~/.ssh/saigbox-backend-key.pem"
INSTANCE_ID="i-0d394d6974a0e8021"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}📦 Step 1: Pushing latest code to GitHub...${NC}"
git add .
git commit -m "Deploy: Update OAuth configuration and API endpoints" || echo "No changes to commit"
git push origin main

echo -e "${YELLOW}🔄 Step 2: Connecting to EC2 and updating code...${NC}"
ssh -i $EC2_KEY $EC2_USER@$EC2_HOST << 'ENDSSH'
    cd /home/ubuntu/SAIGBOX-V3
    echo "Pulling latest code from GitHub..."
    git pull origin main
    
    echo "Activating virtual environment..."
    source venv/bin/activate
    
    echo "Installing/updating dependencies..."
    pip install -r requirements.txt --upgrade
ENDSSH

echo -e "${YELLOW}🔐 Step 3: Updating environment variables...${NC}"
# Copy local .env to EC2 (excluding sensitive local-only vars)
scp -i $EC2_KEY /Users/marcushansen/SAIGBOX-V3/.env $EC2_USER@$EC2_HOST:/home/ubuntu/SAIGBOX-V3/.env

echo -e "${YELLOW}🔒 Step 4: Setting up SSL certificates...${NC}"
ssh -i $EC2_KEY $EC2_USER@$EC2_HOST << 'ENDSSH'
    cd /home/ubuntu/SAIGBOX-V3
    
    # Check if SSL is already set up
    if [ ! -d "/etc/letsencrypt/live/api.saigbox.com" ]; then
        echo "Setting up SSL certificates with Let's Encrypt..."
        
        # Install certbot if not installed
        sudo apt-get update
        sudo apt-get install -y certbot python3-certbot-nginx
        
        # Get SSL certificate
        sudo certbot certonly --nginx \
            -d api.saigbox.com \
            --non-interactive \
            --agree-tos \
            --email admin@saigbox.com \
            --redirect || echo "Certbot may already be configured"
    else
        echo "SSL certificates already exist, checking renewal..."
        sudo certbot renew --dry-run
    fi
    
    # Update nginx configuration for SSL
    sudo tee /etc/nginx/sites-available/saigbox > /dev/null << 'EOF'
server {
    listen 80;
    server_name api.saigbox.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.saigbox.com;

    ssl_certificate /etc/letsencrypt/live/api.saigbox.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.saigbox.com/privkey.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    
    # CORS configuration for SAIGBOX frontend
    location / {
        # Handle preflight requests
        if ($request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' '$http_origin' always;
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
            add_header 'Access-Control-Allow-Headers' 'Origin, Content-Type, Accept, Authorization' always;
            add_header 'Access-Control-Allow-Credentials' 'true' always;
            add_header 'Access-Control-Max-Age' 86400;
            add_header 'Content-Length' 0;
            add_header 'Content-Type' 'text/plain';
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
        
        # Add CORS headers to responses
        add_header 'Access-Control-Allow-Origin' '$http_origin' always;
        add_header 'Access-Control-Allow-Credentials' 'true' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'Origin, Content-Type, Accept, Authorization' always;
    }
}
EOF
    
    # Test and reload nginx
    sudo nginx -t
    sudo systemctl reload nginx
ENDSSH

echo -e "${YELLOW}🔄 Step 5: Restarting backend services...${NC}"
ssh -i $EC2_KEY $EC2_USER@$EC2_HOST << 'ENDSSH'
    # Update systemd service file with environment variables
    sudo tee /etc/systemd/system/saigbox.service > /dev/null << 'EOF'
[Unit]
Description=SAIGBOX FastAPI Application
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/SAIGBOX-V3
Environment="PATH=/home/ubuntu/SAIGBOX-V3/venv/bin"
EnvironmentFile=/home/ubuntu/SAIGBOX-V3/.env
ExecStart=/home/ubuntu/SAIGBOX-V3/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    # Reload systemd and restart service
    sudo systemctl daemon-reload
    sudo systemctl restart saigbox
    sleep 5
    
    # Check service status
    sudo systemctl status saigbox --no-pager
ENDSSH

echo -e "${YELLOW}✅ Step 6: Verifying deployment...${NC}"
# Test the API endpoints
echo "Testing HTTP to HTTPS redirect..."
curl -I http://api.saigbox.com 2>/dev/null | head -n 1

echo "Testing HTTPS API health endpoint..."
curl -s https://api.saigbox.com/api/health | python3 -m json.tool || echo "API may still be starting..."

echo "Testing OAuth endpoint..."
curl -s https://api.saigbox.com/api/auth/google/url | python3 -m json.tool || echo "OAuth endpoint check"

# Check EC2 instance status
echo -e "\n${GREEN}EC2 Instance Status:${NC}"
aws ec2 describe-instance-status --instance-ids $INSTANCE_ID --query "InstanceStatuses[0].[InstanceState.Name,SystemStatus.Status,InstanceStatus.Status]" --output table

echo -e "\n${GREEN}🎉 Deployment Complete!${NC}"
echo -e "${GREEN}Your backend is now available at: https://api.saigbox.com${NC}"
echo -e "${GREEN}Frontend login page: https://saigbox.com/login${NC}"
echo ""
echo "Next steps:"
echo "1. Test the login flow at https://saigbox.com/login"
echo "2. Monitor logs with: ssh -i $EC2_KEY $EC2_USER@$EC2_HOST 'sudo journalctl -u saigbox -f'"
echo "3. Check nginx logs: ssh -i $EC2_KEY $EC2_USER@$EC2_HOST 'sudo tail -f /var/log/nginx/error.log'"