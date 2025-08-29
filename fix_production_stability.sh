#!/bin/bash

# Script to fix production server stability issues

INSTANCE_ID="i-0d394d6974a0e8021"
EC2_IP="3.233.250.55"
EC2_USER="ubuntu"

echo "🔧 Fixing production server stability..."

# Get availability zone
AZ=$(aws ec2 describe-instances --instance-ids $INSTANCE_ID --query 'Reservations[0].Instances[0].Placement.AvailabilityZone' --output text)

# Setup SSH
TEMP_KEY="/tmp/ec2-fix-$$"
ssh-keygen -t rsa -f "$TEMP_KEY" -N "" -q
aws ec2-instance-connect send-ssh-public-key \
    --instance-id $INSTANCE_ID \
    --instance-os-user $EC2_USER \
    --ssh-public-key "file://${TEMP_KEY}.pub" \
    --availability-zone $AZ > /dev/null 2>&1

# Apply fixes
scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i "$TEMP_KEY" \
    saigbox.service.improved $EC2_USER@$EC2_IP:/tmp/saigbox.service.new

ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i "$TEMP_KEY" $EC2_USER@$EC2_IP << 'ENDSSH'
set -e

echo "=== Backing up current service file ==="
sudo cp /etc/systemd/system/saigbox.service /etc/systemd/system/saigbox.service.backup

echo "=== Installing improved service configuration ==="
sudo mv /tmp/saigbox.service.new /etc/systemd/system/saigbox.service
sudo systemctl daemon-reload

echo "=== Creating monitoring script ==="
cat << 'EOF' > /home/ubuntu/monitor_saigbox.sh
#!/bin/bash
# Simple monitoring script to check service health

while true; do
    if ! systemctl is-active --quiet saigbox; then
        echo "$(date): Service is down, checking..."
        sleep 5
        if ! systemctl is-active --quiet saigbox; then
            echo "$(date): Service still down, investigating..."
            sudo journalctl -u saigbox -n 50 --no-pager > /home/ubuntu/saigbox_crash_$(date +%Y%m%d_%H%M%S).log
        fi
    fi
    sleep 30
done
EOF
chmod +x /home/ubuntu/monitor_saigbox.sh

echo "=== Restarting service with new configuration ==="
sudo systemctl stop saigbox
sleep 2
sudo systemctl start saigbox
sleep 3

echo "=== Checking service status ==="
sudo systemctl status saigbox --no-pager | head -15

echo "=== Testing health endpoint ==="
curl -s http://localhost:8000/health | jq

echo "✅ Stability improvements applied!"
echo ""
echo "Changes made:"
echo "1. Service will only restart on actual failures (not on all exits)"
echo "2. Added memory and CPU limits to prevent resource exhaustion"
echo "3. Added start rate limiting (max 5 restarts in 5 minutes)"
echo "4. Added pre-start cleanup to prevent port conflicts"
echo "5. Created monitoring script at /home/ubuntu/monitor_saigbox.sh"

ENDSSH

# Cleanup
rm -f "$TEMP_KEY" "$TEMP_KEY.pub"

echo "✅ Production server stability fixes applied successfully!"