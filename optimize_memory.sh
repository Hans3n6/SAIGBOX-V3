#!/bin/bash

# Optimize memory usage for SAIGBOX on small EC2 instance

set -e

echo "🔧 Optimizing SAIGBOX for low memory environment..."

INSTANCE_ID="i-0d394d6974a0e8021"
EC2_USER="ubuntu"
EC2_HOST="api.saigbox.com"

# Generate temporary SSH key
TEMP_KEY="/tmp/ec2-optimize-$$"
ssh-keygen -t rsa -f $TEMP_KEY -N "" -q

# Send public key to EC2
aws ec2-instance-connect send-ssh-public-key \
    --instance-id $INSTANCE_ID \
    --instance-os-user $EC2_USER \
    --ssh-public-key file://${TEMP_KEY}.pub \
    --availability-zone us-east-1c

# Optimize configuration
ssh -o StrictHostKeyChecking=no -i $TEMP_KEY $EC2_USER@$EC2_HOST << 'ENDSSH'
    set -e
    
    echo "1. Reducing worker count to save memory..."
    sudo tee /etc/systemd/system/saigbox.service > /dev/null << 'EOF'
[Unit]
Description=SAIGBOX FastAPI Application
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/SAIGBOX-V3
Environment="PATH=/home/ubuntu/SAIGBOX-V3/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
# Use only 1 worker to save memory
ExecStart=/home/ubuntu/SAIGBOX-V3/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 1

# Auto-restart configuration
Restart=always
RestartSec=10
StartLimitInterval=600
StartLimitBurst=5

# Memory limits
MemoryMax=512M
MemoryHigh=400M

# Kill timeout
TimeoutStopSec=10
KillSignal=SIGTERM

[Install]
WantedBy=multi-user.target
EOF

    echo "2. Creating swap file for memory overflow..."
    # Create 1GB swap file
    sudo fallocate -l 1G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    
    # Make swap permanent
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    
    # Adjust swappiness
    echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
    sudo sysctl vm.swappiness=10
    
    echo "3. Clearing system cache..."
    sudo sync
    echo 3 | sudo tee /proc/sys/vm/drop_caches
    
    echo "4. Restarting services with optimized settings..."
    sudo systemctl daemon-reload
    sudo systemctl restart saigbox
    sudo systemctl restart nginx
    
    echo "5. Checking status..."
    sleep 5
    free -h
    echo "---"
    sudo systemctl status saigbox --no-pager | head -15
ENDSSH

# Clean up
rm -f $TEMP_KEY ${TEMP_KEY}.pub

echo "✅ Memory optimization complete!"
echo ""
echo "Changes made:"
echo "  - Reduced to 1 worker (saves ~100MB)"
echo "  - Added 1GB swap file for overflow"
echo "  - Set memory limits for service"
echo "  - Cleared system cache"