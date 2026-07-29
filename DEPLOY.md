# Deploy Guide

## Architecture

```
Local:   localhost:8080 → app:8000 → redis
Server:  Bitrix24 → main nginx (80/443, SSL) → astana-nginx (8081) → app:8000 → redis
```

## Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Base: app + redis (port 8080 for local dev) |
| `docker-compose.prod.yml` | Prod: adds nginx on port 8081 |
| `deploy/nginx/bitrix-chat.conf` | nginx config (proxy → app:8000) |

## Local Development

```bash
docker compose up -d
ngrok http 8080
```

## Server Deployment

### 1. Push to GitHub
```bash
git init && git add . && git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USER/astana.git
git push -u origin main
```

### 2. Server Setup
```bash
ssh root@SERVER_IP
curl -fsSL https://get.docker.com | sh
mkdir -p /opt/bitrix-chat && cd /opt/bitrix-chat
git clone https://github.com/YOUR_USER/astana.git .
```

### 3. Configure
```bash
cp .env.example .env
nano .env  # Fill in credentials
sed -i 's/DOMAIN_NAME/YOUR_DOMAIN/g' deploy/nginx/bitrix-chat.conf
```

### 4. Start containers
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### 5. Add proxy in main nginx

Add to your existing nginx config (`/etc/nginx/conf.d/` or sites-available):

```nginx
server {
    listen 443 ssl;
    server_name YOUR_DOMAIN;

    ssl_certificate /etc/letsencrypt/live/YOUR_DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/YOUR_DOMAIN/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
nginx -t && systemctl reload nginx
```

### 6. Reinstall Bitrix24 App
Delete old app → Install with `BITRIX_APP_WEBHOOK_URL=https://YOUR_DOMAIN/webhooks/bitrix24/app/YOUR_SECRET`

### 7. Test
```bash
curl http://localhost:8081/health
docker compose logs -f
```
