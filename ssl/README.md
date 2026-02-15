# SSL Configuration

## Quick Start

```bash
# Generate SSL certificate
./setup-ssl.sh

# Run with SSL (development)
make run-ssl

# Or with Docker (production)
docker compose up -d
```

## Access Points

- **HTTPS**: https://localhost:8443 (dev) or https://localhost (docker)
- **HTTP**: http://localhost (auto-redirects to HTTPS)

## Production Setup

### Option 1: Let's Encrypt (Free)

```bash
# Install certbot
sudo apt install certbot

# Get certificate for your domain
sudo certbot certonly --standalone -d yourdomain.com

# Update nginx/nginx-ssl.conf
ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

# Auto-renewal
sudo certbot renew --dry-run
```

### Option 2: Custom Certificate

```bash
# Place your certificates
cp your-cert.pem ssl/certs/cert.pem
cp your-key.pem ssl/certs/key.pem

# Restart services
docker compose restart nginx
```

## SSL Configuration Details

- **Protocols**: TLSv1.2, TLSv1.3
- **Ciphers**: HIGH:!aNULL:!MD5
- **HTTP/2**: Enabled
- **Auto-redirect**: HTTP → HTTPS

## Troubleshooting

**Browser warning "Not Secure":**
- Self-signed certs show warnings (normal for dev)
- Click "Advanced" → "Proceed to localhost"

**Certificate expired:**
```bash
./setup-ssl.sh  # Regenerate
```

**NGINX not starting:**
```bash
# Check logs
docker compose logs nginx

# Verify cert files exist
ls -la ssl/certs/
```
