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
TEMP_KEY="/tmp/ec2-fix-port-$$"
ssh-keygen -t rsa -f "$TEMP_KEY" -N "" -q

# Send SSH key to EC2
aws ec2-instance-connect send-ssh-public-key \
    --instance-id $INSTANCE_ID \
    --availability-zone $AZ \
    --instance-os-user $EC2_USER \
    --ssh-public-key file://"${TEMP_KEY}.pub" \
    --region $REGION > /dev/null

# Fix port conflict
ssh -o StrictHostKeyChecking=no -i "$TEMP_KEY" $EC2_USER@$EC2_HOST << 'ENDSSH'
echo "=== Checking for port 8000 usage ==="
sudo lsof -i :8000

echo "=== Killing any process on port 8000 ==="
sudo fuser -k 8000/tcp || true

echo "=== Restarting service ==="
sudo systemctl restart saigbox.service

echo "=== Checking service status ==="
sudo systemctl status saigbox.service --no-pager | head -20
ENDSSH

# Clean up
rm -f "$TEMP_KEY" "$TEMP_KEY.pub"
