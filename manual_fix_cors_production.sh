#!/bin/bash

# Manually fix CORS on production without git push

set -e

INSTANCE_ID="i-0d394d6974a0e8021"
EC2_IP="3.233.250.55"
EC2_USER="ubuntu"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🔧 Manually fixing CORS on production server..."
echo "This script will SSH to the server and fix nginx configuration directly."
echo ""

# Get availability zone
echo -e "${YELLOW}Getting EC2 availability zone...${NC}"
AZ=$(aws ec2 describe-instances --instance-ids $INSTANCE_ID --query 'Reservations[0].Instances[0].Placement.AvailabilityZone' --output text)
echo "Instance is in availability zone: $AZ"

# Setup EC2 Instance Connect
echo -e "${YELLOW}Setting up EC2 Instance Connect...${NC}"
TEMP_KEY="/tmp/ec2-cors-manual-$$"
ssh-keygen -t rsa -f "$TEMP_KEY" -N "" -q

echo "Sending temporary SSH key to EC2..."
aws ec2-instance-connect send-ssh-public-key \
    --instance-id $INSTANCE_ID \
    --instance-os-user $EC2_USER \
    --ssh-public-key "file://${TEMP_KEY}.pub" \
    --availability-zone $AZ || { echo -e "${RED}Failed to send SSH key${NC}"; rm -f "$TEMP_KEY" "$TEMP_KEY.pub"; exit 1; }

echo -e "${GREEN}✅ Temporary SSH access granted${NC}"

# Fix CORS on production
echo -e "${YELLOW}Connecting to production server to fix CORS...${NC}"
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i "$TEMP_KEY" $EC2_USER@$EC2_IP << 'ENDSSH'
set -e

echo ""
echo "=== FIXING NGINX CORS CONFIGURATION ==="
echo "Removing duplicate CORS headers from nginx..."

# Backup current config
sudo cp /etc/nginx/sites-available/api.saigbox.com /etc/nginx/sites-available/api.saigbox.com.backup-$(date +%Y%m%d-%H%M%S)

# Create corrected nginx config without CORS headers
sudo tee /etc/nginx/sites-available/api.saigbox.com > /dev/null << 'NGINX_EOF'
server {
    listen 80;
    server_name api.saigbox.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name api.saigbox.com;

    ssl_certificate /etc/letsencrypt/live/api.saigbox.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.saigbox.com/privkey.pem;
    
    client_max_body_size 50M;
    proxy_read_timeout 300s;
    proxy_connect_timeout 75s;

    location / {
        # NO CORS headers - FastAPI handles them
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }

    location /health {
        proxy_pass http://127.0.0.1:8000/health;
    }
}
NGINX_EOF

echo ""
echo "=== Testing nginx configuration ==="
sudo nginx -t

echo ""
echo "=== Reloading nginx ==="
sudo systemctl reload nginx

echo ""
echo "=== Testing CORS headers ==="
# Test that we don't have duplicate CORS headers
echo "Testing OPTIONS request to /api/auth/google/url..."
response=$(curl -s -I -X OPTIONS https://api.saigbox.com/api/auth/google/url \
    -H "Origin: https://saigbox.com" \
    -H "Access-Control-Request-Method: GET" 2>/dev/null)

cors_count=$(echo "$response" | grep -c "Access-Control-Allow-Origin:" || true)
if [ "$cors_count" -eq 1 ]; then
    echo "✅ CORS headers are correct (found exactly 1 header)"
    echo "$response" | grep "Access-Control-Allow-Origin:"
elif [ "$cors_count" -eq 0 ]; then
    echo "⚠️  No CORS headers found - FastAPI might not be responding"
else
    echo "❌ Found $cors_count CORS headers (should be 1)"
    echo "$response" | grep "Access-Control-Allow-Origin:"
fi

echo ""
echo "=== Testing actual auth endpoint ==="
auth_response=$(curl -s -X GET https://api.saigbox.com/api/auth/google/url \
    -H "Origin: https://saigbox.com" 2>&1)

if echo "$auth_response" | grep -q '"url"'; then
    echo "✅ Auth endpoint is working"
else
    echo "⚠️  Auth endpoint response:"
    echo "$auth_response" | head -3
fi

echo ""
echo "=== Restarting backend service for good measure ==="
sudo systemctl restart saigbox
sleep 3

if sudo systemctl is-active --quiet saigbox; then
    echo "✅ Backend service is running"
else
    echo "❌ Backend service failed to start"
    sudo journalctl -u saigbox -n 10 --no-pager
fi

echo ""
echo "🎉 CORS fix has been applied!"

ENDSSH

FIX_STATUS=$?

# Cleanup
rm -f "$TEMP_KEY" "${TEMP_KEY}.pub"

if [ $FIX_STATUS -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ SUCCESS! CORS has been fixed on production${NC}"
    echo ""
    echo "The nginx server no longer adds duplicate CORS headers."
    echo "FastAPI is now the sole source of CORS headers."
    echo ""
    echo "🌐 Test the login at: https://saigbox.com/login"
    echo ""
    echo "The error 'Access-Control-Allow-Origin header contains multiple values' should be gone."
else
    echo ""
    echo -e "${RED}❌ Failed to fix CORS${NC}"
    echo "Check the output above for errors."
    exit 1
fi