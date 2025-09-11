#!/bin/bash
# Deploy styling consistency fixes to production

echo "Deploying email styling consistency fixes to production..."

# Create temporary SSH key for EC2 Instance Connect
TEMP_KEY="/tmp/ec2-styling-fix-$$"
ssh-keygen -t rsa -f "$TEMP_KEY" -N "" -q

# Send public key to EC2
aws ec2-instance-connect send-ssh-public-key \
    --instance-id i-0d394d6974a0e8021 \
    --instance-os-user ubuntu \
    --ssh-public-key file://"${TEMP_KEY}.pub" \
    --availability-zone us-east-1c \
    --region us-east-1 > /dev/null 2>&1

echo "Uploading updated index.html with styling fixes..."

# Upload the modified file
scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i "$TEMP_KEY" \
    /Users/marcushansen/SAIGBOX-V3/static/index.html \
    ubuntu@3.233.250.55:/home/ubuntu/SAIGBOX-V3/static/

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
echo "✅ Styling consistency fixes deployed successfully!"
echo ""
echo "Changes deployed:"
echo "1. Removed jarring blue background from unread emails"
echo "2. Unread emails now use subtle left border (blue) instead of background"
echo "3. Selected emails have green left border with light gray background"
echo "4. Urgent emails have red left border with white background"
echo "5. Consistent text colors that don't change on selection"
echo "6. Smoother hover effects with subtle shadows"
echo "7. Better visual hierarchy without color changes"
echo "8. Fixed sidebar navigation - no more green text when selected"
echo "9. Sidebar items maintain gray colors with subtle background changes"
ENDSSH

# Clean up
rm -f "$TEMP_KEY" "${TEMP_KEY}.pub"

echo ""
echo "Deployment complete!"