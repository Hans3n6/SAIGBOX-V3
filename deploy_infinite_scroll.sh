#!/bin/bash
# Deploy infinite scroll feature to production

echo "Deploying infinite scroll feature to production..."

# Create temporary SSH key for EC2 Instance Connect
TEMP_KEY="/tmp/ec2-infinite-scroll-$$"
ssh-keygen -t rsa -f "$TEMP_KEY" -N "" -q

# Send public key to EC2
aws ec2-instance-connect send-ssh-public-key \
    --instance-id i-0d394d6974a0e8021 \
    --instance-os-user ubuntu \
    --ssh-public-key file://"${TEMP_KEY}.pub" \
    --availability-zone us-east-1c \
    --region us-east-1 > /dev/null 2>&1

echo "Uploading updated files..."

# Upload the modified files
scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i "$TEMP_KEY" \
    /Users/marcushansen/SAIGBOX-V3/static/index.html \
    ubuntu@3.233.250.55:/home/ubuntu/SAIGBOX-V3/static/

scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i "$TEMP_KEY" \
    /Users/marcushansen/SAIGBOX-V3/static/dashboard-index.html \
    ubuntu@3.233.250.55:/home/ubuntu/SAIGBOX-V3/static/

scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i "$TEMP_KEY" \
    /Users/marcushansen/SAIGBOX-V3/api/routes/emails.py \
    ubuntu@3.233.250.55:/home/ubuntu/SAIGBOX-V3/api/routes/

# Restart the service
ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i "$TEMP_KEY" ubuntu@3.233.250.55 << 'ENDSSH'
echo "Restarting SAIGBOX service..."
sudo systemctl restart saigbox
sleep 3

# Check if service is running
if sudo systemctl is-active --quiet saigbox; then
    echo "✅ Service restarted successfully"
else
    echo "❌ Service failed to start"
    sudo journalctl -u saigbox -n 20 --no-pager
    exit 1
fi

echo ""
echo "✅ Infinite scroll feature deployed successfully!"
echo ""
echo "Changes deployed:"
echo "1. Fixed infinite loop issue at page boundaries"
echo "2. Limited auto-loading to first 50 pages (2500 emails)"
echo "3. Added error handling to stop after 3 consecutive failures"
echo "4. Backend returns actual pagination state"
echo "5. Frontend handles infinite scroll intelligently"
echo "6. Prevents server overload from repeated failed requests"
ENDSSH

# Clean up
rm -f "$TEMP_KEY" "${TEMP_KEY}.pub"

echo ""
echo "Deployment complete!"