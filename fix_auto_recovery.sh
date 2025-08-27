#!/bin/bash

# Simple auto-recovery fix for SAIGBOX
set -e

echo "🔧 Fixing SAIGBOX auto-recovery..."

# Configuration
INSTANCE_ID="i-0d394d6974a0e8021"
EC2_USER="ubuntu"
EC2_HOST="api.saigbox.com"

# Generate temporary SSH key
TEMP_KEY="/tmp/ec2-connect-fix-$$"
ssh-keygen -t rsa -f $TEMP_KEY -N "" -q

# Send public key to EC2
aws ec2-instance-connect send-ssh-public-key \
    --instance-id $INSTANCE_ID \
    --instance-os-user $EC2_USER \
    --ssh-public-key file://${TEMP_KEY}.pub \
    --availability-zone us-east-1c

# Fix the systemd service
ssh -o StrictHostKeyChecking=no -i $TEMP_KEY $EC2_USER@$EC2_HOST << 'ENDSSH'
    set -e
    
    # Create simplified systemd service
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

# Auto-restart configuration
Restart=always
RestartSec=10
StartLimitInterval=600
StartLimitBurst=5

# Kill timeout
TimeoutStopSec=10
KillSignal=SIGTERM

[Install]
WantedBy=multi-user.target
EOF

    # Create simple health check script
    sudo tee /usr/local/bin/check-saigbox.sh > /dev/null << 'EOF'
#!/bin/bash
# Simple health check that restarts if needed

if ! curl -f -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "$(date): Service not responding, restarting..." >> /var/log/saigbox-monitor.log
    sudo systemctl restart saigbox
    sleep 5
    sudo systemctl restart nginx
fi
EOF
    
    sudo chmod +x /usr/local/bin/check-saigbox.sh
    
    # Add cron job for monitoring
    (crontab -l 2>/dev/null | grep -v check-saigbox; echo "*/2 * * * * /usr/local/bin/check-saigbox.sh") | crontab -
    
    # Reload and restart
    sudo systemctl daemon-reload
    sudo systemctl enable saigbox
    sudo systemctl restart saigbox
    sleep 5
    sudo systemctl restart nginx
    
    echo "✅ Auto-recovery configured!"
    sudo systemctl status saigbox --no-pager | head -15
ENDSSH

# Clean up
rm -f $TEMP_KEY $TEMP_KEY.pub

echo "✅ Auto-recovery setup complete!"
echo ""
echo "The server will now:"
echo "  - Auto-restart within 10 seconds if it crashes"
echo "  - Health check every 2 minutes"
echo "  - Auto-restart nginx if needed"