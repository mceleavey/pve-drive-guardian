#!/usr/bin/env bash
# ==============================================================================
# Proxmox Drive Guardian — Uninstaller
# ==============================================================================
set -e

if [ "$EUID" -ne 0 ]; then
  echo "Please run as root."
  exit 1
fi

echo "Uninstalling Proxmox Drive Guardian..."
systemctl stop pve-drive-guardian.service 2>/dev/null || true
systemctl disable pve-drive-guardian.service 2>/dev/null || true
rm -f /etc/systemd/system/pve-drive-guardian.service
systemctl daemon-reload

rm -rf /opt/pve-drive-guardian
rm -f /usr/local/bin/pve-drive-guardian /usr/local/bin/drive-guardian

echo "Proxmox Drive Guardian has been removed. Configs retained in /etc/pve-drive-guardian (delete manually if desired)."
