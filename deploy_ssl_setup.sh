#!/bin/bash

# SSL Setup and Final Deployment Script
set -e

echo "🔒 Setting up SSL for api.saigbox.com..."

# Configuration
INSTANCE_ID="i-0d394d6974a0e8021"
EC2_USER="ubuntu"
EC2_HOST="api.saigbox.com"  # Now using domain name
REGION="us-east-1"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}📦 Step 1: Updating environment variables...${NC}"
# Generate temporary SSH key for EC2 Instance Connect
TEMP_KEY="/tmp/ec2-connect-ssl-$$"
ssh-keygen -t rsa -f $TEMP_KEY -N "" -q

# Send public key to EC2
aws ec2-instance-connect send-ssh-public-key \
    --instance-id $INSTANCE_ID \
    --instance-os-user $EC2_USER \
    --ssh-public-key file://${TEMP_KEY}.pub \
    --availability-zone us-east-1c

# Copy updated .env with real credentials
scp -o StrictHostKeyChecking=no -i $TEMP_KEY /Users/marcushansen/SAIGBOX-V3/.env $EC2_USER@$EC2_HOST:/home/ubuntu/SAIGBOX-V3/.env

echo -e "${YELLOW}🔒 Step 2: Installing and configuring SSL...${NC}"
ssh -o StrictHostKeyChecking=no -i $TEMP_KEY $EC2_USER@$EC2_HOST << 'ENDSSH'
    set -e
    cd /home/ubuntu/SAIGBOX-V3
    
    # Install certbot if needed
    if ! command -v certbot &> /dev/null; then
        echo "Installing certbot..."
        sudo apt-get update
        sudo apt-get install -y certbot python3-certbot-nginx
    fi
    
    # Stop nginx temporarily for certbot standalone mode
    sudo systemctl stop nginx
    
    # Get SSL certificate
    echo "Obtaining SSL certificate from Let's Encrypt..."
    sudo certbot certonly --standalone \
        -d api.saigbox.com \
        --non-interactive \
        --agree-tos \
        --email admin@saigbox.com \
        --no-eff-email
    
    # Configure nginx with SSL
    echo "Configuring nginx with SSL..."
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
    
    # CORS configuration
    location / {
        # Let FastAPI handle all CORS including preflight requests
        
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
        
        # CORS is handled by FastAPI, not nginx - don't add headers here
    }
}
EOF
    
    # Test nginx configuration
    sudo nginx -t
    
    # Start nginx
    sudo systemctl start nginx
    sudo systemctl reload nginx
    
    # Set up auto-renewal
    echo "Setting up automatic certificate renewal..."
    (crontab -l 2>/dev/null; echo "0 3 * * * /usr/bin/certbot renew --quiet --nginx") | crontab -
    
    # Restart FastAPI with updated environment
    echo "Restarting FastAPI with updated credentials..."
    sudo systemctl restart saigbox
    
    echo "Waiting for services to stabilize..."
    sleep 5
    
    # Check status
    sudo systemctl status saigbox --no-pager | head -20
ENDSSH

# Clean up temporary key
rm -f $TEMP_KEY $TEMP_KEY.pub

echo -e "${YELLOW}✅ Step 3: Verifying HTTPS setup...${NC}"

# Test HTTPS redirect
echo "Testing HTTP to HTTPS redirect..."
curl -I http://api.saigbox.com 2>/dev/null | head -n 1

# Test HTTPS endpoint
echo "Testing HTTPS endpoint..."
curl -s https://api.saigbox.com/docs | grep -o "<title>.*</title>" || echo "Checking..."

# Test OAuth endpoint with real credentials
echo "Testing OAuth endpoint..."
curl -s https://api.saigbox.com/api/auth/google/url | python3 -c "import sys, json; data = json.load(sys.stdin); print('✅ OAuth URL generated' if 'url' in data and 'YOUR_NEW_CLIENT_ID' not in data['url'] else '⚠️  Check credentials')"

echo ""
echo -e "${GREEN}🎉 SSL Setup Complete!${NC}"
echo ""
echo "Your secure API is now available at:"
echo "  ${GREEN}https://api.saigbox.com${NC}"
echo ""
echo "Test the login flow at:"
echo "  ${GREEN}https://saigbox.com/login${NC}"
echo ""
echo "API Documentation:"
echo "  ${GREEN}https://api.saigbox.com/docs${NC}"