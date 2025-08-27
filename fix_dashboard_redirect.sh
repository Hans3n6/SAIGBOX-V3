#!/bin/bash

echo "🔄 Fixing dashboard redirect..."

# Generate temporary SSH key
TEMP_KEY="/tmp/ec2-fix-redirect-$$"
ssh-keygen -t rsa -f $TEMP_KEY -N "" -q

# Send public key to EC2
aws ec2-instance-connect send-ssh-public-key \
    --instance-id i-0d394d6974a0e8021 \
    --instance-os-user ubuntu \
    --ssh-public-key file://${TEMP_KEY}.pub \
    --availability-zone us-east-1c > /dev/null 2>&1

# Fix the redirect
ssh -o StrictHostKeyChecking=no -i $TEMP_KEY ubuntu@api.saigbox.com << 'EOF'
cd /home/ubuntu/SAIGBOX-V3

# Update the redirect URLs in main.py
sed -i 's|RedirectResponse(url="/")|RedirectResponse(url="https://dashboard.saigbox.com")|g' api/main.py

# Also update error redirects
sed -i 's|RedirectResponse(url="/login|RedirectResponse(url="https://saigbox.com/login|g' api/main.py

# Show what was changed
echo "Updated OAuth callback redirects:"
grep -n 'RedirectResponse(url="https://dashboard.saigbox.com")' api/main.py | head -3

echo ""
echo "Updated error redirects:"
grep -n 'RedirectResponse(url="https://saigbox.com/login' api/main.py | head -3

# Restart the service
sudo systemctl restart saigbox
echo ""
echo "✅ Service restarted with new redirect URLs"
EOF

# Clean up
rm -f $TEMP_KEY $TEMP_KEY.pub

echo ""
echo "✅ Dashboard redirect fixed!"
echo "Now OAuth callbacks will redirect to: https://dashboard.saigbox.com"