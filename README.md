# 🛡️ Proxmox Drive Guardian (`pve-drive-guardian`)

> **Autonomous Storage Intelligence, Thermal Protection & Bad Sector Shield for Proxmox VE & Linux Homelabs.**  
> Protects aging/failing hard drives, prevents overheating, eliminates spurious spinup polling, isolates bad sectors, and autonomously evacuates critical storage archives.

---

## 🚀 Key Features

* **❄️ Closed-Loop Thermal Governor**: Dynamic spindle spin-down (`hdparm -y`) and cooling thresholds that reduce overheated drive temperatures by **15°C–20°C**.
* **🛡️ Bad Sector Degradation Shield**: Detects pending/reallocated sectors, enforces **Read-Only (`ro,noatime,noload`)** protection, and tunes Linux kernel block device timeouts (`15s`) with `mq-deadline` to prevent system lockups.
* **🔄 Autonomous Low-Impact Data Rescue**: Evacuates Proxmox backup archives and mirrors critical folders to healthy storage pools using idle I/O priority (`ionice -c 3`, `nice -n 19`) while preserving secure permissions (`--chmod`).
* **💤 Standby-Preserving Zero-Wake Telemetry**: Replaces naive polling loops with `hdparm -C` and `smartctl -n standby` to **never wake sleeping disks**.
* **🔒 Hardened Security Architecture**: Defaults to **Localhost (`127.0.0.1`)** binding, optional **API Token Authentication**, strict device regular-expression validation, and path traversal boundary checks.
* **🎛️ Modern Web Dashboard & REST API**: Dark-theme responsive UI running on port `8095` with real-time health grades, thermal gauges, rescue progress bars, and one-click emergency controls.
* **🖥️ Interactive Terminal CLI**: Manage and monitor storage arrays directly using `drive-guardian status`, `drive-guardian cool`, and `drive-guardian safe-mount`.

---

## 📊 Feature Comparison

| Feature | Standard `smartmontools` | Generic Homelab Tools | 🛡️ Proxmox Drive Guardian |
| :--- | :---: | :---: | :---: |
| **SMART Telemetry** | ⚠️ Email only | ⚠️ Wakes sleeping drives | ✅ **Zero-Wake Polling** (`-n standby`) |
| **Overheating Mitigation** | ❌ None | ❌ None | ✅ **Closed-loop Standby Cooldown** |
| **Bad Sector Protection** | ❌ Passive logs | ❌ None | ✅ **Read-Only Shield + 15s Timeout** |
| **Autonomous Data Evacuation** | ❌ Manual | ❌ Manual | ✅ **Low-Impact Background Stream** |
| **Web UI & CLI Utility** | ❌ None | ⚠️ Heavyweight | ✅ **Built-in Ultra-Fast Dashboard** |
| **Security & Auth Control** | ❌ N/A | ⚠️ Open by default | ✅ **Localhost-by-default + Token Auth** |

---

## ⚡ 1-Line Quick Install

Run this command directly in the Proxmox VE host shell (or any Debian/Ubuntu server):

```bash
curl -fsSL https://raw.githubusercontent.com/mceleavey/pve-drive-guardian/main/install.sh | bash
```

*Or install from local source:*

```bash
git clone https://github.com/mceleavey/pve-drive-guardian.git
cd pve-drive-guardian
chmod +x install.sh && ./install.sh
```

---

## 🖥️ Command-Line Interface (CLI)

```bash
# View storage health matrix, temperatures, and live rescue operations
drive-guardian status

# View live data evacuation and mirror progress
drive-guardian rescue

# Force emergency cooldown standby on an overheating drive
drive-guardian cool /dev/sdf

# Enforce read-only shield mode on a degrading drive partition
drive-guardian safe-mount /dev/sde1

# View recent autonomous interventions log
drive-guardian logs
```

---

## 🌐 Web Dashboard (Port 8095)

By default, the Web UI and REST API listen on `127.0.0.1:8095` for local security.

* **Access locally or via SSH Tunnel:**
  ```bash
  ssh -L 8095:127.0.0.1:8095 root@<your-proxmox-ip>
  ```
  Then open `http://localhost:8095/` in your local browser.

* **Exposing on LAN or Reverse Proxy:**
  Change `"api_host": "0.0.0.0"` in `/etc/pve-drive-guardian/config.json` and set an `"api_token"` to protect API write actions.

---

## 🔒 Security Architecture & Hardening

1. **Localhost Binding by Default**: The API server binds strictly to `127.0.0.1` out-of-the-box to prevent unauthenticated network exposure.
2. **API Token Authentication**: State-modifying actions (forcing standby, mounting read-only, triggering rescue jobs) support bearer token authentication via `api_token` in `config.json` (`Authorization: Bearer <token>` or `X-API-Key: <token>`).
3. **Command Injection Prevention**: Low-level system utilities (`hdparm`, `smartctl`, `mount`, `rsync`) are invoked via explicit array-based argument lists (`shell=False`) with strict timeouts.
4. **Strict Device Regex Validation**: All device identifiers must match strict block device patterns (`^/dev/(sd[a-z][0-9]*|nvme[0-9]n[0-9](p[0-9]+)?)$`).
5. **Path Traversal & Storage Boundary Protection**: All rescue paths are resolved and checked against forbidden system roots (`/`, `/etc`, `/proc`, `/sys`, `/dev`, `/etc/pve`, `/root/.ssh`).
6. **Permission Preservation (`rsync_chmod`)**: Rescue synchronization applies strict permission masking (`--chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r`) to prevent confidential backup files from becoming world-readable.

---

## ⚙️ Configuration (`/etc/pve-drive-guardian/config.json`)

```json
{
  "guardian": {
    "version": "2.4.1",
    "poll_interval_seconds": 15,
    "api_host": "127.0.0.1",
    "api_port": 8095,
    "api_token": "your-secret-token-here",
    "web_ui_enabled": true,
    "log_file": "/var/log/pve-drive-guardian.log",
    "state_file": "/var/lib/pve-drive-guardian/state.json"
  },
  "thermal_governor": {
    "enabled": true,
    "warning_temp_c": 45,
    "critical_temp_c": 52,
    "cooldown_target_temp_c": 40,
    "default_hdd_standby_minutes": 3,
    "auto_spindown_on_overheat": true
  },
  "degradation_shield": {
    "enabled": true,
    "auto_remount_ro_on_bad_sectors": true,
    "min_pending_sectors_trigger": 1,
    "min_reallocated_sectors_trigger": 50,
    "kernel_block_timeout_seconds": 15,
    "optimal_scheduler": "mq-deadline"
  },
  "rescue_engine": {
    "enabled": false,
    "source_path": "/mnt/source-drive",
    "target_path": "/mnt/backup-pool",
    "rsync_chmod": "Du=rwx,Dgo=rx,Fu=rw,Fgo=r",
    "ionice_class": 3,
    "nice_level": 19,
    "auto_redirect_proxmox_vzdump": false
  },
  "protected_system_drives": [
    "/dev/sda"
  ]
}
```

---

## 📄 License
MIT License. Open-source and free for the Proxmox and Homelab community.
