#!/bin/bash

# Improved deployment script with better service management

set -e

INSTANCE_ID="i-0d394d6974a0e8021"
EC2_IP="3.233.250.55"
EC2_USER="ubuntu"
REPO_URL="https://github.com/Hans3n6/SAIGBOX-V3.git"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🚀 Deploying SAIGBOX Backend via EC2 Instance Connect..."

# Step 1: Commit and push any local changes
echo -e "${YELLOW}📦 Step 1: Committing and pushing latest code...${NC}"
git add -A 2>/dev/null || true
if git diff --staged --quiet 2>/dev/null; then
    echo "No changes to commit"
else
    git commit -m "Deploy: $(date '+%Y-%m-%d %H:%M:%S')" || true
    git push origin main || { echo -e "${RED}Failed to push to GitHub${NC}"; exit 1; }
fi

# Step 2: Get correct availability zone
echo -e "${YELLOW}🔍 Step 2: Getting EC2 availability zone...${NC}"
AZ=$(aws ec2 describe-instances --instance-ids $INSTANCE_ID --query 'Reservations[0].Instances[0].Placement.AvailabilityZone' --output text)
echo "Instance is in availability zone: $AZ"

# Step 3: Setup EC2 Instance Connect
echo -e "${YELLOW}🔑 Step 3: Setting up EC2 Instance Connect...${NC}"
TEMP_KEY="/tmp/ec2-deploy-$$"
ssh-keygen -t rsa -f "$TEMP_KEY" -N "" -q

echo "Sending temporary SSH key to EC2..."
aws ec2-instance-connect send-ssh-public-key \
    --instance-id $INSTANCE_ID \
    --instance-os-user $EC2_USER \
    --ssh-public-key "file://${TEMP_KEY}.pub" \
    --availability-zone $AZ || { echo -e "${RED}Failed to send SSH key${NC}"; rm -f "$TEMP_KEY" "$TEMP_KEY.pub"; exit 1; }

echo -e "${GREEN}✅ Temporary SSH access granted for 60 seconds${NC}"

# Step 4: Deploy to EC2
echo -e "${YELLOW}🔄 Step 4: Deploying to EC2...${NC}"
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i "$TEMP_KEY" $EC2_USER@$EC2_IP << 'ENDSSH'
set -e

echo "=== Pulling latest code ==="
cd /home/ubuntu/SAIGBOX-V3
git fetch origin
git reset --hard origin/main

echo "=== Installing dependencies ==="
source venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

echo "=== Gracefully stopping current service ==="
sudo systemctl stop saigbox
sleep 2

echo "=== Checking for port conflicts ==="
sudo lsof -ti:8000 | xargs -r sudo kill -9 2>/dev/null || true

echo "=== Starting service ==="
sudo systemctl start saigbox
sleep 3

echo "=== Verifying service status ==="
if sudo systemctl is-active --quiet saigbox; then
    echo "✅ Service is running"
    sudo systemctl status saigbox --no-pager | head -10
else
    echo "❌ Service failed to start"
    sudo journalctl -u saigbox -n 20 --no-pager
    exit 1
fi

echo "=== Testing health endpoint ==="
for i in {1..5}; do
    if curl -s http://localhost:8000/health | grep -q "healthy"; then
        echo "✅ Health check passed"
        break
    fi
    if [ $i -eq 5 ]; then
        echo "❌ Health check failed after 5 attempts"
        exit 1
    fi
    echo "Waiting for service to be ready... (attempt $i/5)"
    sleep 2
done

ENDSSH

DEPLOY_STATUS=$?

# Cleanup
rm -f "$TEMP_KEY" "$TEMP_KEY.pub"

if [ $DEPLOY_STATUS -eq 0 ]; then
    echo -e "${GREEN}🎉 Deployment Complete!${NC}"
    echo ""
    echo "Your backend is accessible at:"
    echo "  - http://$EC2_IP"
    echo "  - https://api.saigbox.com"
else
    echo -e "${RED}❌ Deployment failed!${NC}"
    echo "Check the logs above for details."
    exit 1
fi