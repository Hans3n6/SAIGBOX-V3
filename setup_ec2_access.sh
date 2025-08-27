#!/bin/bash

# Setup EC2 SSH Access Script
echo "🔑 Setting up SSH access to your EC2 instance..."

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

INSTANCE_ID="i-0d394d6974a0e8021"
KEY_NAME="saigbox-backend-key"

echo -e "${YELLOW}Checking for existing key pair...${NC}"

# Check if key pair exists in AWS
KEY_EXISTS=$(aws ec2 describe-key-pairs --key-names $KEY_NAME 2>/dev/null | grep KeyName)

if [ -z "$KEY_EXISTS" ]; then
    echo -e "${YELLOW}Key pair not found in AWS. Creating new key pair...${NC}"
    
    # Create new key pair
    aws ec2 create-key-pair --key-name $KEY_NAME --query 'KeyMaterial' --output text > ~/.ssh/${KEY_NAME}.pem
    
    # Set correct permissions
    chmod 400 ~/.ssh/${KEY_NAME}.pem
    
    echo -e "${GREEN}✅ New key pair created and saved to ~/.ssh/${KEY_NAME}.pem${NC}"
    echo -e "${YELLOW}⚠️  You'll need to update your EC2 instance to use this new key${NC}"
else
    echo -e "${YELLOW}Key pair exists in AWS.${NC}"
    
    if [ ! -f ~/.ssh/${KEY_NAME}.pem ]; then
        echo -e "${YELLOW}⚠️  Key file not found locally at ~/.ssh/${KEY_NAME}.pem${NC}"
        echo ""
        echo "Options:"
        echo "1. If you have the .pem file elsewhere, copy it to: ~/.ssh/${KEY_NAME}.pem"
        echo "   Then run: chmod 400 ~/.ssh/${KEY_NAME}.pem"
        echo ""
        echo "2. Use AWS Systems Manager Session Manager (no SSH key needed):"
        echo "   aws ssm start-session --target $INSTANCE_ID"
        echo ""
        echo "3. Create a new key pair and update the instance (requires stopping the instance)"
    else
        echo -e "${GREEN}✅ Key file found at ~/.ssh/${KEY_NAME}.pem${NC}"
        chmod 400 ~/.ssh/${KEY_NAME}.pem
    fi
fi

echo ""
echo -e "${GREEN}Testing connection methods:${NC}"

# Test SSH connection
if [ -f ~/.ssh/${KEY_NAME}.pem ]; then
    echo "Testing SSH connection..."
    ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -i ~/.ssh/${KEY_NAME}.pem ubuntu@3.233.250.55 "echo 'SSH connection successful!'" || echo "SSH connection failed"
fi

# Check if Session Manager is available
echo ""
echo "Checking AWS Systems Manager access..."
aws ssm describe-instance-information --filters "Key=InstanceIds,Values=$INSTANCE_ID" --query "InstanceInformationList[0].PingStatus" --output text 2>/dev/null || echo "Session Manager not configured"

echo ""
echo -e "${GREEN}Instance Security Group:${NC}"
aws ec2 describe-security-groups --group-ids $(aws ec2 describe-instances --instance-ids $INSTANCE_ID --query "Reservations[0].Instances[0].SecurityGroups[0].GroupId" --output text) --query "SecurityGroups[0].IpPermissions[?FromPort==\`22\` || FromPort==\`80\` || FromPort==\`443\`].[FromPort,ToPort,IpProtocol,IpRanges[0].CidrIp]" --output table

echo ""
echo "Next steps:"
echo "1. If SSH doesn't work, ensure security group allows SSH (port 22) from your IP"
echo "2. If you don't have the .pem file, you can use AWS Systems Manager Session Manager"
echo "3. Or contact whoever set up the EC2 instance for the SSH key file"