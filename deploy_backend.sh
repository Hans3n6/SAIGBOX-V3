#!/bin/bash

# Backend deployment script for AWS EC2
# This script sets up the FastAPI backend on an EC2 instance

echo "Setting up SAIGBOX Backend on EC2..."

# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install Python 3.11
sudo apt-get install -y python3.11 python3.11-venv python3-pip

# Install nginx
sudo apt-get install -y nginx

# Clone repository
cd /home/ubuntu
git clone https://github.com/Hans3n6/SAIGBOX-V3.git
cd SAIGBOX-V3

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Create systemd service for the app
sudo tee /etc/systemd/system/saigbox.service > /dev/null <<EOF
[Unit]
Description=SAIGBOX FastAPI Application
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/SAIGBOX-V3
Environment="PATH=/home/ubuntu/SAIGBOX-V3/venv/bin"
ExecStart=/home/ubuntu/SAIGBOX-V3/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Configure nginx
sudo tee /etc/nginx/sites-available/saigbox > /dev/null <<EOF
server {
    listen 80;
    server_name api.saigbox.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# Enable site
sudo ln -s /etc/nginx/sites-available/saigbox /etc/nginx/sites-enabled
sudo nginx -t
sudo systemctl restart nginx

# Start service
sudo systemctl enable saigbox
sudo systemctl start saigbox

echo "Backend deployment complete!"
echo "API should be accessible at http://api.saigbox.com"
echo "Don't forget to:"
echo "1. Set up SSL with certbot"
echo "2. Configure security groups to allow HTTP/HTTPS"
echo "3. Set up environment variables in /etc/systemd/system/saigbox.service"