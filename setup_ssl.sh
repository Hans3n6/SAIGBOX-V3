#!/bin/bash

# SSL Setup Script for SAIGBOX Backend API
# This script configures SSL/HTTPS for api.saigbox.com using Let's Encrypt

echo "Setting up SSL for api.saigbox.com..."

# Install certbot
sudo apt-get update
sudo apt-get install -y certbot python3-certbot-nginx

# Stop nginx temporarily to get certificate
sudo systemctl stop nginx

# Get SSL certificate from Let's Encrypt
sudo certbot certonly --standalone \
    -d api.saigbox.com \
    --non-interactive \
    --agree-tos \
    --email admin@saigbox.com \
    --redirect

# Update nginx configuration with SSL
sudo tee /etc/nginx/sites-available/saigbox > /dev/null <<'EOF'
server {
    listen 80;
    server_name api.saigbox.com;
    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name api.saigbox.com;

    # SSL certificates from Let's Encrypt
    ssl_certificate /etc/letsencrypt/live/api.saigbox.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.saigbox.com/privkey.pem;
    
    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options DENY;
    add_header X-XSS-Protection "1; mode=block";

    # CORS headers for SAIGBOX frontend
    add_header 'Access-Control-Allow-Origin' 'https://saigbox.com' always;
    add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
    add_header 'Access-Control-Allow-Headers' 'Origin, Content-Type, Accept, Authorization' always;
    add_header 'Access-Control-Allow-Credentials' 'true' always;

    location / {
        # Handle preflight requests
        if ($request_method = 'OPTIONS') {
            add_header 'Access-Control-Allow-Origin' 'https://saigbox.com' always;
            add_header 'Access-Control-Allow-Methods' 'GET, POST, PUT, DELETE, OPTIONS' always;
            add_header 'Access-Control-Allow-Headers' 'Origin, Content-Type, Accept, Authorization' always;
            add_header 'Access-Control-Allow-Credentials' 'true' always;
            add_header 'Access-Control-Max-Age' 86400;
            add_header 'Content-Type' 'text/plain; charset=utf-8';
            add_header 'Content-Length' 0;
            return 204;
        }

        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_read_timeout 86400;
    }
}
EOF

# Test nginx configuration
sudo nginx -t

# Restart nginx
sudo systemctl restart nginx

# Set up automatic certificate renewal
echo "0 0,12 * * * root certbot renew --quiet --no-self-upgrade --post-hook 'systemctl reload nginx'" | sudo tee -a /etc/crontab > /dev/null

echo "✅ SSL setup complete!"
echo ""
echo "Your API is now available at: https://api.saigbox.com"
echo ""
echo "Important notes:"
echo "1. Make sure DNS for api.saigbox.com points to IP: 3.233.250.55"
echo "2. Security group should allow ports 80 and 443"
echo "3. Certificate will auto-renew every 12 hours"
echo ""
echo "To verify SSL certificate:"
echo "  curl https://api.saigbox.com/api/health"