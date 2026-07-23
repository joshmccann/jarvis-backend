#!/usr/bin/env bash
# One-paste JARVIS installer for a fresh Ubuntu VPS. Run as root:
#   curl -fsSL https://raw.githubusercontent.com/joshmccann/jarvis-backend/main/install.sh | bash
set -e
apt-get update -y && apt-get install -y python3 git curl
mkdir -p /opt && cd /opt
[ -d jarvis ] || git clone https://github.com/joshmccann/jarvis-backend jarvis
cd jarvis && git pull --ff-only || true
[ -f .env ] || cp .env.example .env
cat >/etc/systemd/system/jarvis.service <<UNIT
[Unit]
Description=JARVIS backend
After=network.target
[Service]
WorkingDirectory=/opt/jarvis
EnvironmentFile=/opt/jarvis/.env
ExecStart=/usr/bin/python3 /opt/jarvis/server.py
Restart=always
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload && systemctl enable --now jarvis
echo ""
echo "==================================================================="
echo " JARVIS is running on port 8080 (server IP :8080)."
echo " 1) Edit your keys:   nano /opt/jarvis/.env"
echo " 2) Restart:          systemctl restart jarvis"
echo " 3) For the mic to work you need HTTPS — see README (Cloudflare Tunnel, free)."
echo "==================================================================="
