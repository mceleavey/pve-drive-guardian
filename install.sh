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
CYAN="\033[1;36m"
NC="\033[0m"

NON_INTERACTIVE=false

# Parse command line flags
for arg in "$@"; do
  case "$arg" in
    -y|--yes|-q|--quiet|--non-interactive)
      NON_INTERACTIVE=true
      ;;
  esac
done

if [ -n "$DEBIAN_FRONTEND" ] && [ "$DEBIAN_FRONTEND" = "noninteractive" ]; then
  NON_INTERACTIVE=true
fi

echo -e "${BLUE}============================================================================${NC}"
echo -e "${GREEN} 🛡️  Installing Proxmox Drive Guardian (pve-drive-guardian)...${NC}"
echo -e "${BLUE}============================================================================${NC}"

# 1. Pre-execution Privileges Check
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}[-] Error: Installer must be run as root (or with sudo).${NC}"
  exit 1
fi

# 2. Operating System Check
if [ ! -f /etc/debian_version ] && ! command -v apt-get >/dev/null 2>&1; then
  echo -e "${RED}[-] Error: Proxmox Drive Guardian is designed for Debian-based systems (Proxmox VE, Debian, Ubuntu).${NC}"
  exit 1
fi

# 3. Systemd Environment Check
if [ ! -d /run/systemd/system ] && ! pidof systemd >/dev/null 2>&1; then
  echo -e "${RED}[-] Error: Systemd init system not detected. Systemd is required to run the guardian daemon service.${NC}"
  exit 1
fi

# 4. Python3 Runtime Check
if ! command -v python3 >/dev/null 2>&1; then
  echo -e "${YELLOW}[*] Python 3 is not installed. Installing standard package dependencies...${NC}"
  apt-get update -qq && apt-get install -y -qq python3 >/dev/null 2>&1
fi

if ! python3 -c 'import sys; exit(0 if sys.version_info >= (3, 6) else 1)' 2>/dev/null; then
  echo -e "${RED}[-] Error: Python 3.6 or higher is required.${NC}"
  exit 1
fi

echo -e "${GREEN}[+] Pre-execution environment checks passed.${NC}"

# Optional confirmation prompt if interactive
if [ "$NON_INTERACTIVE" = false ] && [ -t 0 ]; then
  echo -e "${CYAN}The installer will:${NC}"
  echo -e "  • Install required system tools: smartmontools, hdparm, rsync, python3"
  echo -e "  • Deploy daemon to /opt/pve-drive-guardian"
  echo -e "  • Configure local service listening on 127.0.0.1:8095"
  echo -e "  • Register and start systemd service: pve-drive-guardian.service"
  echo -e "  • Link CLI utility to /usr/local/bin/drive-guardian"
  read -r -p "Do you want to proceed with the installation? [Y/n] " response
  response=${response,,} # tolower
  if [[ "$response" =~ ^(no|n)$ ]]; then
    echo -e "${YELLOW}[*] Installation cancelled by user.${NC}"
    exit 0
  fi
fi

# 5. Dependency Verification & Installation
echo -e "${BLUE}[*] Verifying required system tools (smartmontools, hdparm, rsync, python3)...${NC}"
apt-get update -qq
apt-get install -y -qq smartmontools hdparm rsync python3 >/dev/null 2>&1
echo -e "${GREEN}[+] Dependencies verified and ready.${NC}"

# 6. Secure Directory Setup
INSTALL_DIR="/opt/pve-drive-guardian"
CONFIG_DIR="/etc/pve-drive-guardian"
STATE_DIR="/var/lib/pve-drive-guardian"

mkdir -p "$INSTALL_DIR"
mkdir -p -m 750 "$CONFIG_DIR"
mkdir -p -m 750 "$STATE_DIR"

# 7. Copy Application Files
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp -r "$SCRIPT_DIR/src/"* "$INSTALL_DIR/"

if [ ! -f "$CONFIG_DIR/config.json" ]; then
  cp "$SCRIPT_DIR/src/config.json.example" "$CONFIG_DIR/config.json"
  chmod 640 "$CONFIG_DIR/config.json"
  echo -e "${GREEN}[+] Default configuration installed to $CONFIG_DIR/config.json (640 permissions).${NC}"
fi

chmod +x "$INSTALL_DIR/guardian_daemon.py"
chmod +x "$INSTALL_DIR/guardian_cli.py"

# 8. Symlink CLI Utilities
cat << 'EOF' > /usr/local/bin/pve-drive-guardian
#!/usr/bin/env bash
python3 /opt/pve-drive-guardian/guardian_cli.py "$@"
EOF
chmod 755 /usr/local/bin/pve-drive-guardian
ln -sf /usr/local/bin/pve-drive-guardian /usr/local/bin/drive-guardian

# 9. Register Systemd Service Unit
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
UMask=0027

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable pve-drive-guardian.service
systemctl restart pve-drive-guardian.service

IP_ADDR=$(hostname -I | awk '{print $1}')
echo -e "${GREEN}============================================================================${NC}"
echo -e "${GREEN} ✅ Proxmox Drive Guardian successfully installed and active!${NC}"
echo -e "${BLUE} 🌐 Web Dashboard:${NC} http://127.0.0.1:8095/ (or http://${IP_ADDR}:8095/ if api_host='0.0.0.0')"
echo -e "${BLUE} 🖥️  CLI Utility:${NC}   drive-guardian status"
echo -e "${BLUE} ⚙️  Config File:${NC}    $CONFIG_DIR/config.json"
echo -e "${CYAN} 🔒 Security Note:${NC}  Default binding is 127.0.0.1 (Localhost). Set api_token in config for auth."
echo -e "${GREEN}============================================================================${NC}"
