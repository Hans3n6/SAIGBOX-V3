#\!/bin/bash

# EC2 Instance details
INSTANCE_ID="i-0d394d6974a0e8021"
EC2_HOST="3.233.250.55"
EC2_USER="ubuntu"
REGION="us-east-1"

# Get availability zone
AZ=$(aws ec2 describe-instances \
    --instance-ids $INSTANCE_ID \
    --query 'Reservations[0].Instances[0].Placement.AvailabilityZone' \
    --region $REGION \
    --output text)

# Create temporary SSH key
TEMP_KEY="/tmp/ec2-check-$$"
ssh-keygen -t rsa -f "$TEMP_KEY" -N "" -q

# Send SSH key to EC2
aws ec2-instance-connect send-ssh-public-key \
    --instance-id $INSTANCE_ID \
    --availability-zone $AZ \
    --instance-os-user $EC2_USER \
    --ssh-public-key file://"${TEMP_KEY}.pub" \
    --region $REGION > /dev/null

# Check nginx configuration
ssh -o StrictHostKeyChecking=no -i "$TEMP_KEY" $EC2_USER@$EC2_HOST << 'ENDSSH'
echo "=== Checking nginx sites ==="
ls -la /etc/nginx/sites-available/
ls -la /etc/nginx/sites-enabled/

echo "=== Checking default nginx config ==="
sudo grep -r "Access-Control" /etc/nginx/ 2>/dev/null || echo "No Access-Control headers found"

echo "=== Checking if nginx is running ==="
sudo systemctl status nginx --no-pager | head -10
ENDSSH

# Clean up
rm -f "$TEMP_KEY" "$TEMP_KEY.pub"
