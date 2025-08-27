#!/bin/bash

# Connect to EC2 and setup backend
EC2_IP="54.172.3.112"
KEY_PATH="~/saigbox-backend-key.pem"

echo "Connecting to EC2 instance at $EC2_IP"
echo "Setting up SAIGBOX Backend..."

# Copy deployment script
scp -i $KEY_PATH -o StrictHostKeyChecking=no deploy_backend.sh ubuntu@$EC2_IP:~/

# Execute deployment
ssh -i $KEY_PATH -o StrictHostKeyChecking=no ubuntu@$EC2_IP "chmod +x deploy_backend.sh && ./deploy_backend.sh"

echo "Backend setup initiated on EC2"