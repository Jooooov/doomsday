#!/usr/bin/env bash
# Run on a fresh Ubuntu 22.04 / Debian 12 VPS to set up the server.
# Usage: bash setup-vps.sh yourdomain.com your@email.com
set -euo pipefail

DOMAIN="${1:?Usage: $0 <domain> <email>}"
EMAIL="${2:?Usage: $0 <domain> <email>}"
APP_DIR="/opt/doomsday"

echo "=== 1. System packages ==="
apt-get update -qq
apt-get install -y -qq git curl ufw fail2ban certbot nginx-common

echo "=== 2. Docker ==="
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh
  usermod -aG docker "$USER" || true
fi

echo "=== 3. Firewall ==="
ufw allow OpenSSH
ufw allow 80
ufw allow 443
ufw --force enable

echo "=== 4. Clone repo ==="
if [ -d "$APP_DIR" ]; then
  echo "  $APP_DIR already exists — pulling latest"
  git -C "$APP_DIR" pull
else
  git clone https://github.com/Jooooov/doomsday.git "$APP_DIR"
fi

echo "=== 5. TLS certificate (Let's Encrypt) ==="
mkdir -p "$APP_DIR/nginx/certs"
# Temporary nginx for ACME challenge
docker run --rm -d --name tmp-nginx -p 80:80 \
  -v "$APP_DIR/nginx/certs:/etc/nginx/certs" \
  nginx:alpine sh -c "mkdir -p /var/www/certbot && nginx -g 'daemon off;'" 2>/dev/null || true

certbot certonly \
  --standalone \
  --preferred-challenges http \
  --agree-tos --no-eff-email \
  -m "$EMAIL" \
  -d "$DOMAIN" \
  --cert-path "$APP_DIR/nginx/certs/fullchain.pem" \
  --key-path  "$APP_DIR/nginx/certs/privkey.pem"  || \
certbot certonly \
  --standalone --agree-tos --no-eff-email \
  -m "$EMAIL" -d "$DOMAIN"

# Copy certs to app dir
cp /etc/letsencrypt/live/"$DOMAIN"/fullchain.pem "$APP_DIR/nginx/certs/"
cp /etc/letsencrypt/live/"$DOMAIN"/privkey.pem   "$APP_DIR/nginx/certs/"

echo "=== 6. Configure nginx.conf domain ==="
sed -i "s/DOMAIN_PLACEHOLDER/$DOMAIN/g" "$APP_DIR/nginx/nginx.conf"

echo "=== 7. Auto-renew certs (cron) ==="
(crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet && cp /etc/letsencrypt/live/$DOMAIN/*.pem $APP_DIR/nginx/certs/ && docker exec doomsday-nginx nginx -s reload") | crontab -

echo ""
echo "VPS setup complete!"
echo ""
echo "Next steps:"
echo "  1. Copy your .env to $APP_DIR/.env"
echo "  2. cd $APP_DIR && docker compose -f docker-compose.prod.yml up -d --build"
echo "  3. Add GitHub secrets: VPS_HOST, VPS_USER, VPS_SSH_KEY, PROD_ENV"
