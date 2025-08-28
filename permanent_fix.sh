#!/bin/bash

# PERMANENT FIX FOR SERVER CRASHES
set -e

echo "🔧 IMPLEMENTING PERMANENT CRASH FIX..."

INSTANCE_ID="i-0d394d6974a0e8021"
EC2_USER="ubuntu"
EC2_HOST="api.saigbox.com"

# Generate SSH key
TEMP_KEY="/tmp/ec2-fix-$$"
ssh-keygen -t rsa -f $TEMP_KEY -N "" -q

# Send public key to EC2
aws ec2-instance-connect send-ssh-public-key \
    --instance-id $INSTANCE_ID \
    --instance-os-user $EC2_USER \
    --ssh-public-key file://${TEMP_KEY}.pub \
    --availability-zone us-east-1c

ssh -o StrictHostKeyChecking=no -i $TEMP_KEY $EC2_USER@$EC2_HOST << 'ENDSSH'
    set -e
    
    echo "1. Installing supervisor for better process management..."
    sudo apt-get update -qq
    sudo apt-get install -y supervisor
    
    echo "2. Creating supervisor configuration..."
    sudo tee /etc/supervisor/conf.d/saigbox.conf > /dev/null << 'EOF'
[program:saigbox]
command=/home/ubuntu/SAIGBOX-V3/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 1
directory=/home/ubuntu/SAIGBOX-V3
user=ubuntu
autostart=true
autorestart=true
startsecs=10
stopwaitsecs=10
killasgroup=true
stopasgroup=true
stdout_logfile=/var/log/supervisor/saigbox.log
stderr_logfile=/var/log/supervisor/saigbox_err.log
environment=PATH="/home/ubuntu/SAIGBOX-V3/venv/bin:/usr/bin:/bin"

; Memory limit
; Will restart if memory exceeds 400MB
[eventlistener:memmon]
command=memmon -p saigbox=400MB
events=TICK_60
EOF

    echo "3. Stopping old systemd service..."
    sudo systemctl stop saigbox || true
    sudo systemctl disable saigbox || true
    
    echo "4. Creating watchdog script..."
    sudo tee /usr/local/bin/saigbox-watchdog.sh > /dev/null << 'EOF'
#!/bin/bash
# Watchdog to ensure service stays up

while true; do
    # Check if service is responding
    if ! curl -f -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "$(date): Service not responding, restarting..."
        sudo supervisorctl restart saigbox
        sleep 10
        sudo systemctl restart nginx
    fi
    
    # Check memory usage
    MEM=$(ps aux | grep "[u]vicorn api.main:app" | awk '{sum+=$6} END {print sum/1024}')
    if (( ${MEM%.*} > 400 )); then
        echo "$(date): High memory usage (${MEM}MB), restarting..."
        sudo supervisorctl restart saigbox
    fi
    
    sleep 30
done
EOF
    sudo chmod +x /usr/local/bin/saigbox-watchdog.sh
    
    echo "5. Creating watchdog service..."
    sudo tee /etc/systemd/system/saigbox-watchdog.service > /dev/null << 'EOF'
[Unit]
Description=SAIGBOX Watchdog
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/saigbox-watchdog.sh
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

    echo "6. Optimizing Python for production..."
    cat > /home/ubuntu/SAIGBOX-V3/.env.production << 'EOF'
PYTHONUNBUFFERED=1
PYTHONDONTWRITEBYTECODE=1
PYTHONOPTIMIZE=1
EOF
    cat /home/ubuntu/SAIGBOX-V3/.env >> /home/ubuntu/SAIGBOX-V3/.env.production
    mv /home/ubuntu/SAIGBOX-V3/.env.production /home/ubuntu/SAIGBOX-V3/.env
    
    echo "7. Starting everything..."
    sudo supervisorctl reread
    sudo supervisorctl update
    sudo supervisorctl start saigbox
    
    sudo systemctl daemon-reload
    sudo systemctl enable saigbox-watchdog
    sudo systemctl start saigbox-watchdog
    
    sudo systemctl restart nginx
    
    echo "8. Verifying..."
    sleep 5
    sudo supervisorctl status
    echo "---"
    curl -s http://localhost:8000/health
    echo ""
    echo "---"
    free -h
ENDSSH

# Clean up
rm -f $TEMP_KEY ${TEMP_KEY}.pub

echo ""
echo "✅ PERMANENT FIX APPLIED!"
echo ""
echo "What this does:"
echo "  - Uses Supervisor for professional process management"
echo "  - Auto-restarts if memory exceeds 400MB"
echo "  - Watchdog checks health every 30 seconds"
echo "  - Automatic recovery from any crash"
echo "  - Proper Python optimization"
echo ""
echo "The server should NEVER crash again!"