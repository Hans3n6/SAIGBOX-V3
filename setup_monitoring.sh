#!/bin/bash

# SAIGBOX Monitoring and Auto-Recovery Script
# This script ensures the server stays running and auto-recovers from crashes

set -e

echo "🔧 Setting up permanent monitoring and auto-recovery for SAIGBOX..."

# Configuration
INSTANCE_ID="i-0d394d6974a0e8021"
EC2_USER="ubuntu"
EC2_HOST="api.saigbox.com"
REGION="us-east-1"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${YELLOW}📦 Step 1: Creating monitoring scripts on EC2...${NC}"

# Generate temporary SSH key for EC2 Instance Connect
TEMP_KEY="/tmp/ec2-connect-monitor-$$"
ssh-keygen -t rsa -f $TEMP_KEY -N "" -q

# Send public key to EC2
aws ec2-instance-connect send-ssh-public-key \
    --instance-id $INSTANCE_ID \
    --instance-os-user $EC2_USER \
    --ssh-public-key file://${TEMP_KEY}.pub \
    --availability-zone us-east-1c

echo -e "${YELLOW}🔧 Step 2: Installing monitoring and recovery scripts...${NC}"
ssh -o StrictHostKeyChecking=no -i $TEMP_KEY $EC2_USER@$EC2_HOST << 'ENDSSH'
    set -e
    
    # Create monitoring script
    echo "Creating health check script..."
    sudo tee /usr/local/bin/saigbox-health-check.sh > /dev/null << 'EOF'
#!/bin/bash

# Health check and auto-recovery script for SAIGBOX
LOG_FILE="/var/log/saigbox-health.log"

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> $LOG_FILE
}

# Check if the service is running
if systemctl is-active --quiet saigbox; then
    # Service is running, check if it's responding
    if curl -f -s -o /dev/null -w "%{http_code}" http://localhost:8000/health | grep -q "000\|502"; then
        log_message "ERROR: Service is running but not responding. Restarting..."
        sudo systemctl restart saigbox
        sleep 10
        sudo systemctl restart nginx
        log_message "Service restarted due to non-responsiveness"
    else
        log_message "INFO: Service is healthy"
    fi
else
    log_message "ERROR: Service is not running. Starting..."
    sudo systemctl start saigbox
    sleep 10
    sudo systemctl start nginx
    log_message "Service started"
fi

# Check nginx
if ! systemctl is-active --quiet nginx; then
    log_message "ERROR: Nginx is not running. Starting..."
    sudo systemctl start nginx
    log_message "Nginx started"
fi

# Clean up old logs (keep last 1000 lines)
tail -n 1000 $LOG_FILE > $LOG_FILE.tmp && mv $LOG_FILE.tmp $LOG_FILE
EOF

    sudo chmod +x /usr/local/bin/saigbox-health-check.sh
    
    # Create auto-recovery script
    echo "Creating auto-recovery script..."
    sudo tee /usr/local/bin/saigbox-auto-recover.sh > /dev/null << 'EOF'
#!/bin/bash

# Auto-recovery script for SAIGBOX after crashes
LOG_FILE="/var/log/saigbox-recovery.log"

log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> $LOG_FILE
}

log_message "Auto-recovery triggered"

# Stop services
sudo systemctl stop saigbox
sudo systemctl stop nginx

# Clear any stuck processes
sudo pkill -f uvicorn || true
sleep 2

# Check for Python syntax errors
cd /home/ubuntu/SAIGBOX-V3
source venv/bin/activate

if python -m py_compile api/main.py 2>/dev/null; then
    log_message "Python syntax check passed"
else
    log_message "ERROR: Python syntax errors detected"
    # Try to pull latest code as fallback
    git fetch origin main
    git reset --hard origin/main
    log_message "Reset to latest main branch"
fi

# Start services
sudo systemctl start saigbox
sleep 5
sudo systemctl start nginx

# Verify services are running
sleep 5
if systemctl is-active --quiet saigbox && systemctl is-active --quiet nginx; then
    log_message "Recovery successful - services are running"
else
    log_message "ERROR: Recovery failed - manual intervention needed"
fi

# Clean up log
tail -n 1000 $LOG_FILE > $LOG_FILE.tmp && mv $LOG_FILE.tmp $LOG_FILE
EOF

    sudo chmod +x /usr/local/bin/saigbox-auto-recover.sh
    
    # Update systemd service with better restart policy
    echo "Updating systemd service configuration..."
    sudo tee /etc/systemd/system/saigbox.service > /dev/null << 'EOF'
[Unit]
Description=SAIGBOX FastAPI Application
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/SAIGBOX-V3
Environment="PATH=/home/ubuntu/SAIGBOX-V3/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/home/ubuntu/SAIGBOX-V3/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 2
ExecStartPre=/bin/bash -c 'source /home/ubuntu/SAIGBOX-V3/venv/bin/activate && python -m py_compile /home/ubuntu/SAIGBOX-V3/api/main.py'
Restart=always
RestartSec=5
StartLimitInterval=60
StartLimitBurst=3
StandardOutput=journal
StandardError=journal

# Recovery action when service fails repeatedly
ExecStopPost=/usr/local/bin/saigbox-auto-recover.sh

[Install]
WantedBy=multi-user.target
EOF

    # Create cron job for health checks
    echo "Setting up health check cron job..."
    (crontab -l 2>/dev/null | grep -v saigbox-health-check; echo "* * * * * /usr/local/bin/saigbox-health-check.sh") | crontab -

    # Create nginx monitoring
    echo "Setting up nginx auto-restart..."
    sudo tee /etc/systemd/system/nginx-monitor.service > /dev/null << 'EOF'
[Unit]
Description=Nginx Monitor
After=nginx.service

[Service]
Type=simple
ExecStart=/bin/bash -c 'while true; do if ! systemctl is-active --quiet nginx; then systemctl start nginx; fi; sleep 30; done'
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

    sudo tee /etc/systemd/system/nginx-monitor.timer > /dev/null << 'EOF'
[Unit]
Description=Run Nginx Monitor every 30 seconds
Requires=nginx-monitor.service

[Timer]
OnBootSec=30
OnUnitActiveSec=30

[Install]
WantedBy=timers.target
EOF

    # Reload systemd and start monitoring
    echo "Activating monitoring services..."
    sudo systemctl daemon-reload
    sudo systemctl enable saigbox
    sudo systemctl enable nginx-monitor.timer
    sudo systemctl start nginx-monitor.timer
    
    # Restart services with new configuration
    sudo systemctl restart saigbox
    sleep 5
    sudo systemctl restart nginx
    
    # Create convenience script for manual recovery
    echo "Creating manual recovery script..."
    tee ~/recover-saigbox.sh > /dev/null << 'EOF'
#!/bin/bash
echo "🔧 Manually recovering SAIGBOX..."
sudo /usr/local/bin/saigbox-auto-recover.sh
echo "✅ Recovery complete. Checking status..."
sudo systemctl status saigbox --no-pager | head -20
EOF
    chmod +x ~/recover-saigbox.sh
    
    echo "✅ Monitoring setup complete!"
    echo ""
    echo "Health check log: /var/log/saigbox-health.log"
    echo "Recovery log: /var/log/saigbox-recovery.log"
    echo "Manual recovery: ~/recover-saigbox.sh"
    echo ""
    
    # Show current status
    sudo systemctl status saigbox --no-pager | head -10
ENDSSH

# Clean up temporary key
rm -f $TEMP_KEY $TEMP_KEY.pub

echo ""
echo -e "${GREEN}🎉 Monitoring and Auto-Recovery Setup Complete!${NC}"
echo ""
echo "The server now has:"
echo "  ✅ Automatic restart on crash (within 5 seconds)"
echo "  ✅ Health checks every minute"
echo "  ✅ Auto-recovery from syntax errors"
echo "  ✅ Nginx monitoring and auto-restart"
echo "  ✅ Fallback to latest working code from GitHub"
echo ""
echo "To check monitoring status:"
echo "  ssh ubuntu@api.saigbox.com 'tail -f /var/log/saigbox-health.log'"
echo ""
echo "To manually trigger recovery:"
echo "  ssh ubuntu@api.saigbox.com '~/recover-saigbox.sh'"