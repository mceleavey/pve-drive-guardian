# 🛡️ Proxmox Drive Guardian (`pve-drive-guardian`)

> **Autonomous Storage AI & Thermal Protection System for Proxmox VE & Linux Homelabs.**  
> Protects aging/failing hard drives, prevents overheating, eliminates spurious spinup polling, isolates bad sectors, and autonomously evacuates critical VM/LXC backups to healthy storage.

---

## 🚀 Key Features

* **❄️ Closed-Loop Thermal Governor**: Dynamic spindle spin-down (`hdparm -y`) and cooling thresholds that reduce overheated drive temperatures by **15°C–20°C**.
* **🛡️ Bad Sector Degradation Shield**: Detects pending/reallocated sectors, enforces **Read-Only (`ro,noatime,noload`)** protection, and tunes Linux kernel block device timeouts (`15s`) with `mq-deadline` to prevent system freezes.
* **🔄 Autonomous Low-Impact Data Rescue**: Evacuates Proxmox backup archives and mirrors critical folders to healthy storage pools using idle I/O priority (`ionice -c 3`, `nice -n 19`).
* **💤 Standby-Preserving Zero-Wake Telemetry**: Replaces naive polling loops with `hdparm -C` and `smartctl -n standby` to **never wake sleeping disks**.
* **🎛️ Modern Web Dashboard & REST API**: Dark-theme responsive UI running on port `8095` with real-time health grades, thermal gauges, rescue progress bars, and one-click emergency controls.
* **🖥️ Interactive Terminal CLI**: Manage and monitor your storage arrays from anywhere using `drive-guardian status`.

---

## 📊 How It Compares

| Feature | Standard `smartmontools` | Generic Homelab Tools | 🛡️ Proxmox Drive Guardian |
| :--- | :---: | :---: | :---: |
| **SMART Telemetry** | ⚠️ Email only | ⚠️ Wakes sleeping drives | ✅ **Zero-Wake Polling** (`-n standby`) |
| **Overheating Mitigation** | ❌ None | ❌ None | ✅ **Closed-loop Standby Cooldown** |
| **Bad Sector Protection** | ❌ Passive logs | ❌ None | ✅ **Read-Only Shield + 15s Timeout** |
| **Proxmox vzdump Redirection** | ❌ None | ❌ None | ✅ **Auto-migrates backup schedules** |
| **Autonomous Data Evacuation** | ❌ Manual | ❌ Manual | ✅ **Low-Impact Background Stream** |
| **Web UI & CLI Utility** | ❌ None | ⚠️ Heavyweight | ✅ **Built-in Ultra-Fast Dashboard** |

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

# Enforce read-only shield mode on a degrading drive
drive-guardian safe-mount /dev/sde1

# View recent autonomous interventions log
drive-guardian logs
```

---

## 🌐 Web Dashboard (Port 8095)

Access the live web dashboard in your browser:
```
http://<your-proxmox-ip>:8095/
```

---

## ⚙️ Configuration (`/etc/pve-drive-guardian/config.json`)

```json
{
  "guardian": {
    "poll_interval_seconds": 15,
    "api_port": 8095
  },
  "thermal_governor": {
    "enabled": true,
    "warning_temp_c": 45,
    "critical_temp_c": 52,
    "cooldown_target_temp_c": 40,
    "default_hdd_standby_minutes": 3
  },
  "degradation_shield": {
    "enabled": true,
    "auto_remount_ro_on_bad_sectors": true,
    "kernel_block_timeout_seconds": 15,
    "optimal_scheduler": "mq-deadline"
  },
  "rescue_engine": {
    "auto_evacuate_failing_drives": true,
    "default_safe_storage_pool": "/mnt/media"
  }
}
```

---

## 📄 License
MIT License. Open-source and free for the Proxmox and Homelab community.
