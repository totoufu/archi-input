#!/bin/bash
# =============================================================
# Archi Input – VPS Deploy Script (Ubuntu 24.04)
# Run as root: bash deploy.sh
# =============================================================
set -e

APP_DIR="/opt/archi-input"
REPO_URL="https://github.com/totoufu/archi-input.git"
DOMAIN_OR_IP="163.44.119.69"

echo "=== [1/6] System update & dependencies ==="
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv git nginx

echo "=== [2/6] Clone repository ==="
if [ -d "$APP_DIR" ]; then
    echo "Directory exists, pulling latest..."
    cd "$APP_DIR" && git pull
else
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

echo "=== [3/6] Python venv & packages ==="
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "=== [4/6] Create data & uploads directories ==="
mkdir -p data static/uploads

echo "=== [5/6] Create systemd service ==="
cat > /etc/systemd/system/archi-input.service << 'EOF'
[Unit]
Description=Archi Input Flask App
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/archi-input
Environment="PATH=/opt/archi-input/venv/bin"
ExecStart=/opt/archi-input/venv/bin/gunicorn --workers 2 --bind 127.0.0.1:5000 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable archi-input
systemctl restart archi-input

echo "=== [6/6] Configure nginx ==="
cat > /etc/nginx/sites-available/archi-input << EOF
server {
    listen 80;
    server_name $DOMAIN_OR_IP;

    client_max_body_size 16M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 120s;
    }

    location /static/ {
        alias /opt/archi-input/static/;
        expires 1d;
    }
}
EOF

# Enable site & remove default
ln -sf /etc/nginx/sites-available/archi-input /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx

echo ""
echo "============================================"
echo "  DEPLOY COMPLETE!"
echo "  Access: http://$DOMAIN_OR_IP"
echo "============================================"
echo ""
echo "Useful commands:"
echo "  systemctl status archi-input   # Check app status"
echo "  journalctl -u archi-input -f   # View app logs"
echo "  systemctl restart archi-input  # Restart app"
echo "  cd /opt/archi-input && git pull && systemctl restart archi-input  # Update"
