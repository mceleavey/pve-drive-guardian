#!/usr/bin/env bash
# ==============================================================================
# Proxmox Drive Guardian — 1-Line Community Installer
# GitHub: https://github.com/mceleavey/pve-drive-guardian
# ==============================================================================
set -e

GREEN="\033[1;32m"
BLUE="\033[1;34m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
NC="\033[0m"

echo -e "${BLUE}============================================================================${NC}"
echo -e "${GREEN} 🛡️  Installing Proxmox Drive Guardian (pve-drive-guardian)...${NC}"
echo -e "${BLUE}============================================================================${NC}"

# Check root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}[-] Please run as root.${NC}"
  exit 1
fi

# Ensure dependencies
echo -e "${BLUE}[*] Checking required system tools...${NC}"
apt-get update -qq
apt-get install -y -qq smartmontools hdparm rsync python3 >/dev/null 2>&1
echo -e "${GREEN}[+] Dependencies verified (smartmontools, hdparm, rsync, python3).${NC}"

# Directory setup
INSTALL_DIR="/opt/pve-drive-guardian"
CONFIG_DIR="/etc/pve-drive-guardian"
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "/var/lib/pve-drive-guardian"

# Copy source files
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp -r "$SCRIPT_DIR/src/"* "$INSTALL_DIR/"

if [ ! -f "$CONFIG_DIR/config.json" ]; then
  cp "$SCRIPT_DIR/src/config.json.example" "$CONFIG_DIR/config.json"
  echo -e "${GREEN}[+] Default configuration installed to $CONFIG_DIR/config.json${NC}"
fi

chmod +x "$INSTALL_DIR/guardian_daemon.py"

# Symlink CLI
cat << 'EOF' > /usr/local/bin/pve-drive-guardian
#!/usr/bin/env bash
python3 /opt/pve-drive-guardian/guardian_cli.py "$@"
EOF
chmod +x /usr/local/bin/pve-drive-guardian
ln -sf /usr/local/bin/pve-drive-guardian /usr/local/bin/drive-guardian

# Create systemd service
cat << 'EOF' > /etc/systemd/system/pve-drive-guardian.service
[Unit]
Description=Proxmox Drive Guardian & Storage Protection Autonomous Service
After=network.target local-fs.target
Wants=local-fs.target

[Service]
Type=simple
WorkingDirectory=/opt/pve-drive-guardian
ExecStart=/usr/bin/python3 /opt/pve-drive-guardian/guardian_daemon.py
Restart=always
RestartSec=5
User=root
Nice=10
IOWeight=100

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable pve-drive-guardian.service
systemctl restart pve-drive-guardian.service

IP_ADDR=$(hostname -I | awk '{print $1}')
echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN} ✅ Proxmox Drive Guardian successfully installed and active!${NC}"
echo -e "${BLUE} 🌐 Web Dashboard:${NC} http://${IP_ADDR}:8095/"
echo -e "${BLUE} 🖥️  CLI Utility:${NC}   drive-guardian status"
echo -e "${BLUE} ⚙️  Config File:${NC}    $CONFIG_DIR/config.json"
echo -e "${GREEN}============================================================================${NC}"
