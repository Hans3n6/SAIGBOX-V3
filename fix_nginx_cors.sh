#\!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}🔧 Fixing Nginx CORS Configuration...${NC}"

# EC2 Instance details
INSTANCE_ID="i-0d394d6974a0e8021"
EC2_HOST="3.233.250.55"
EC2_USER="ubuntu"
REGION="us-east-1"

# Get availability zone
echo -e "${YELLOW}Getting EC2 availability zone...${NC}"
AZ=$(aws ec2 describe-instances \
    --instance-ids $INSTANCE_ID \
    --query 'Reservations[0].Instances[0].Placement.AvailabilityZone' \
    --region $REGION \
    --output text)

echo "Instance is in availability zone: $AZ"

# Create temporary SSH key
TEMP_KEY="/tmp/ec2-cors-fix-$$"
ssh-keygen -t rsa -f "$TEMP_KEY" -N "" -q

# Send SSH key to EC2
echo "Sending temporary SSH key to EC2..."
aws ec2-instance-connect send-ssh-public-key \
    --instance-id $INSTANCE_ID \
    --availability-zone $AZ \
    --instance-os-user $EC2_USER \
    --ssh-public-key file://"${TEMP_KEY}.pub" \
    --region $REGION > /dev/null

echo -e "${GREEN}✅ Temporary SSH access granted${NC}"

# Fix nginx configuration
echo -e "${YELLOW}Updating nginx configuration...${NC}"

ssh -o StrictHostKeyChecking=no -i "$TEMP_KEY" $EC2_USER@$EC2_HOST << 'ENDSSH'
# Check current nginx config
echo "=== Current nginx CORS configuration ==="
sudo grep -A2 -B2 "add_header.*Access-Control" /etc/nginx/sites-available/api.saigbox.com || echo "No CORS headers in nginx"

# Remove CORS headers from nginx since FastAPI handles them
echo "=== Removing CORS headers from nginx ==="
sudo cp /etc/nginx/sites-available/api.saigbox.com /etc/nginx/sites-available/api.saigbox.com.backup

# Remove any add_header Access-Control lines from nginx
sudo sed -i '/add_header.*Access-Control/d' /etc/nginx/sites-available/api.saigbox.com

# Test nginx config
echo "=== Testing nginx configuration ==="
sudo nginx -t

# Reload nginx
echo "=== Reloading nginx ==="
sudo systemctl reload nginx

echo "=== Verifying changes ==="
sudo grep -A2 -B2 "add_header.*Access-Control" /etc/nginx/sites-available/api.saigbox.com || echo "✅ CORS headers removed from nginx"

# Show current config
echo "=== Current nginx config (proxy section) ==="
sudo grep -A10 "location / {" /etc/nginx/sites-available/api.saigbox.com

ENDSSH

# Clean up
rm -f "$TEMP_KEY" "$TEMP_KEY.pub"

echo -e "${GREEN}🎉 Nginx CORS configuration fixed\!${NC}"
echo "CORS is now handled only by FastAPI backend"
