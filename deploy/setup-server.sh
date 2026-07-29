#!/bin/bash
set -e

# ============================================
# Server setup script for Bitrix Chat Bot
# Run as root on Ubuntu/Debian
# ============================================

DOMAIN="$1"
APP_DIR="/opt/bitrix-chat"

if [ -z "$DOMAIN" ]; then
    echo "Usage: $0 <domain-name>"
    echo "Example: $0 chat.example.com"
    exit 1
fi

echo "=== Setting up server for $DOMAIN ==="

# 1. Update system
echo "--- Updating system packages ---"
apt update && apt upgrade -y

# 2. Install Docker
echo "--- Installing Docker ---"
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
    rm get-docker.sh
    systemctl enable docker
    systemctl start docker
fi

# 3. Install Docker Compose plugin
echo "--- Installing Docker Compose ---"
if ! docker compose version &> /dev/null; then
    apt install -y docker-compose-plugin
fi

# 4. Install certbot (for SSL, runs on host)
echo "--- Installing certbot ---"
if ! command -v certbot &> /dev/null; then
    apt install -y certbot
fi

# 5. Create app directory
echo "--- Setting up application ---"
mkdir -p "$APP_DIR"

# 6. Create certbot webroot
mkdir -p /var/www/certbot

echo ""
echo "=== Manual steps required ==="
echo ""
echo "1. Clone your repository:"
echo "   cd $APP_DIR"
echo "   git clone https://github.com/YOUR_USER/astana.git ."
echo ""
echo "2. Create .env file with your settings:"
echo "   nano $APP_DIR/.env"
echo ""
echo "3. Get SSL certificate (run BEFORE starting docker):"
echo "   certbot certonly --webroot -w /var/www/certbot -d $DOMAIN"
echo ""
echo "4. Update nginx config with your domain:"
echo "   sed -i 's/DOMAIN_NAME/$DOMAIN/g' $APP_DIR/deploy/nginx/bitrix-chat.conf"
echo ""
echo "5. Start the application (nginx is a Docker container):"
echo "   cd $APP_DIR && docker compose up -d"
echo ""
echo "6. Set up auto-renewal:"
echo "   echo '0 12 * * * certbot renew --quiet && docker compose -f $APP_DIR/docker-compose.yml exec nginx nginx -s reload' | crontab -"
echo ""
echo "=== Done! ==="
