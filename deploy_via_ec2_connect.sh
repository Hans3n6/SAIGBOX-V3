#!/bin/bash

# EC2 Instance Connect Deployment Script
# This uses EC2 Instance Connect for temporary SSH access

set -e

echo "🚀 Deploying SAIGBOX Backend via EC2 Instance Connect..."

# Configuration
INSTANCE_ID="i-0d394d6974a0e8021"
EC2_USER="ubuntu"
EC2_HOST="3.233.250.55"
REGION="us-east-1"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}📦 Step 1: Committing and pushing latest code...${NC}"
git add .
git commit -m "Deploy: Update OAuth configuration and API endpoints" || echo "No changes to commit"
git push origin main || echo "Push failed - you may need to pull first"

echo -e "${YELLOW}🔑 Step 2: Setting up EC2 Instance Connect...${NC}"
# Generate temporary SSH key
TEMP_KEY="/tmp/ec2-connect-key-$$"
ssh-keygen -t rsa -f $TEMP_KEY -N "" -q

# Send public key to EC2 using Instance Connect
echo "Sending temporary SSH key to EC2..."
aws ec2-instance-connect send-ssh-public-key \
    --instance-id $INSTANCE_ID \
    --instance-os-user $EC2_USER \
    --ssh-public-key file://${TEMP_KEY}.pub \
    --availability-zone $(aws ec2 describe-instances --instance-ids $INSTANCE_ID --query "Reservations[0].Instances[0].Placement.AvailabilityZone" --output text)

echo -e "${GREEN}✅ Temporary SSH access granted for 60 seconds${NC}"

echo -e "${YELLOW}🔄 Step 3: Updating code on EC2...${NC}"
ssh -o StrictHostKeyChecking=no -i $TEMP_KEY $EC2_USER@$EC2_HOST << 'ENDSSH'
    set -e
    cd /home/ubuntu/SAIGBOX-V3 || { echo "Project directory not found. Cloning..."; git clone https://github.com/Hans3n6/SAIGBOX-V3.git /home/ubuntu/SAIGBOX-V3; cd /home/ubuntu/SAIGBOX-V3; }
    
    echo "Pulling latest code..."
    git pull origin main || { git stash; git pull origin main; }
    
    # Set up Python environment if needed
    if [ ! -d "venv" ]; then
        echo "Creating virtual environment..."
        python3 -m venv venv
    fi
    
    echo "Activating virtual environment and installing dependencies..."
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt --upgrade
ENDSSH

echo -e "${YELLOW}🔐 Step 4: Updating environment variables...${NC}"
# Copy .env file
scp -o StrictHostKeyChecking=no -i $TEMP_KEY /Users/marcushansen/SAIGBOX-V3/.env $EC2_USER@$EC2_HOST:/home/ubuntu/SAIGBOX-V3/.env

echo -e "${YELLOW}⚙️ Step 5: Configuring services...${NC}"
ssh -o StrictHostKeyChecking=no -i $TEMP_KEY $EC2_USER@$EC2_HOST << 'ENDSSH'
    set -e
    
    # Install nginx if not installed
    if ! command -v nginx &> /dev/null; then
        echo "Installing nginx..."
        sudo apt-get update
        sudo apt-get install -y nginx
    fi
    
    # Create systemd service for FastAPI
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
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
    
    # Configure nginx (without SSL for now)
    sudo tee /etc/nginx/sites-available/saigbox > /dev/null << 'EOF'
server {
    listen 80;
    server_name api.saigbox.com 3.233.250.55;

    location / {
        # CORS headers
        add_header 'Access-Control-Allow-Origin' '*' always;
        add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
        add_header 'Access-Control-Allow-Headers' 'Origin, Content-Type, Accept, Authorization' always;
        
        if ($request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' '*' always;
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
            add_header 'Access-Control-Allow-Headers' 'Origin, Content-Type, Accept, Authorization' always;
            add_header 'Access-Control-Max-Age' 86400;
            add_header 'Content-Length' 0;
            add_header 'Content-Type' 'text/plain';
            return 204;
        }
        
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
    
    # Enable site
    sudo ln -sf /etc/nginx/sites-available/saigbox /etc/nginx/sites-enabled/
    sudo rm -f /etc/nginx/sites-enabled/default
    
    # Test and restart services
    sudo nginx -t
    sudo systemctl daemon-reload
    sudo systemctl enable saigbox
    sudo systemctl restart saigbox
    sudo systemctl restart nginx
    
    echo "Waiting for services to start..."
    sleep 5
    
    # Check status
    sudo systemctl status saigbox --no-pager || true
ENDSSH

# Clean up temporary key
rm -f $TEMP_KEY $TEMP_KEY.pub

echo -e "${YELLOW}✅ Step 6: Verifying deployment...${NC}"

# Test the API
echo "Testing API health endpoint..."
curl -s http://3.233.250.55/api/health | python3 -m json.tool || echo "API may still be starting..."

echo ""
echo -e "${GREEN}🎉 Deployment Complete!${NC}"
echo ""
echo "Your backend is accessible at:"
echo "  - http://3.233.250.55"
echo "  - http://api.saigbox.com (once DNS is configured)"
echo ""
echo "To set up HTTPS:"
echo "1. Ensure DNS A record points api.saigbox.com to 3.233.250.55"
echo "2. Run: ./setup_ssl.sh on the server"
echo ""
echo "To view logs:"
echo "  aws ec2-instance-connect send-ssh-public-key --instance-id $INSTANCE_ID --instance-os-user ubuntu --ssh-public-key file://~/.ssh/id_rsa.pub --availability-zone us-east-1a"
echo "  ssh ubuntu@3.233.250.55 'sudo journalctl -u saigbox -f'"