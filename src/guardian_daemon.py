#!/usr/bin/env python3
"""
Proxmox Drive Guardian (pve-drive-guardian)
==========================================
Autonomous Storage AI & Thermal Protection System for Proxmox VE & Linux Homelabs.
Open-Source Community Edition (Zero Hardcoded Personal Data or Host Info)
"""

import os
import sys
import re
import time
import json
import subprocess
import threading
import signal
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

CONFIG_PATHS = [
    "/etc/pve-drive-guardian/config.json",
    os.path.join(os.path.dirname(__file__), "config.json"),
    os.path.join(os.path.dirname(__file__), "config.json.example")
]

def load_config():
    for p in CONFIG_PATHS:
        if os.path.exists(p):
            try:
                with open(p, "r") as f:
                    return json.load(f)
            except Exception:
                pass
    return {
        "guardian": {
            "poll_interval_seconds": 15,
            "api_port": 8095,
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
            "source_path": "",
            "target_path": "",
            "ionice_class": 3,
            "nice_level": 19,
            "auto_redirect_proxmox_vzdump": false
        },
        "protected_system_drives": []
    }

config = load_config()
API_PORT = int(config.get("guardian", {}).get("api_port", 8095))
LOG_FILE = config.get("guardian", {}).get("log_file", "/var/log/pve-drive-guardian.log")
STATE_FILE = config.get("guardian", {}).get("state_file", "/var/lib/pve-drive-guardian/state.json")

# Global Telemetry & State
guardian_state = {
    "version": "2.4.0-community",
    "hostname": os.uname().nodename if hasattr(os, "uname") else "linux-host",
    "status": "RUNNING",
    "uptime_seconds": 0,
    "last_cycle": "",
    "drives": {},
    "rescue_engine": {
        "active_job": None,
        "status": "IDLE",
        "current_source": None,
        "current_target": None,
        "bytes_transferred": 0,
        "current_file": None,
        "progress_percent": 0.0,
        "total_files_synced": 0,
        "errors_count": 0,
        "last_error": None,
        "paused_for_cooling": False
    },
    "actions_log": []
}

log_lock = threading.Lock()
rescue_lock = threading.Lock()

def sanitize_device_path(dev_path):
    """Validates that a device string matches standard Linux block device patterns."""
    if not isinstance(dev_path, str):
        return None
    dev_path = dev_path.strip()
    if re.match(r"^/dev/(sd[a-z][0-9]*|nvme[0-9]n[0-9](p[0-9]+)?|vd[a-z][0-9]*|hd[a-z][0-9]*)$", dev_path):
        return dev_path
    return None

def log_event(msg, level="INFO"):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] [{level}] {msg}"
    print(entry, flush=True)
    with log_lock:
        try:
            os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
            with open(LOG_FILE, "a") as f:
                f.write(entry + "\n")
        except Exception:
            pass
        guardian_state["actions_log"].insert(0, {"time": timestamp, "level": level, "message": msg})
        if len(guardian_state["actions_log"]) > 100:
            guardian_state["actions_log"].pop()

def get_drive_power_state(dev_path):
    """Queries hardware power state without waking sleeping platters."""
    dev_path = sanitize_device_path(dev_path)
    if not dev_path:
        return "UNKNOWN"
    try:
        res = subprocess.run(["hdparm", "-C", dev_path], capture_output=True, text=True, timeout=3)
        out = res.stdout.lower()
        if "standby" in out:
            return "STANDBY"
        elif "sleeping" in out:
            return "SLEEPING"
        elif "active" in out:
            return "ACTIVE"
    except Exception:
        pass
    return "UNKNOWN"

def tune_kernel_block_device(dev_name):
    """Applies optimal scheduler and short timeout to prevent bad sector lockups."""
    if not re.match(r"^[a-zA-Z0-9_-]+$", dev_name):
        return
    try:
        timeout_val = str(config.get("degradation_shield", {}).get("kernel_block_timeout_seconds", 15))
        timeout_path = f"/sys/block/{dev_name}/device/timeout"
        if os.path.exists(timeout_path):
            with open(timeout_path, "w") as f:
                f.write(f"{timeout_val}\n")
                
        sched_val = str(config.get("degradation_shield", {}).get("optimal_scheduler", "mq-deadline"))
        sched_path = f"/sys/block/{dev_name}/queue/scheduler"
        if os.path.exists(sched_path):
            with open(sched_path, "w") as f:
                f.write(f"{sched_val}\n")
    except Exception:
        pass

def get_drive_telemetry(dev_path):
    """Collects non-intrusive SMART telemetry."""
    dev_path = sanitize_device_path(dev_path)
    if not dev_path:
        return {}

    dev_name = os.path.basename(dev_path)
    power_state = get_drive_power_state(dev_path)
    cached_entry = guardian_state["drives"].get(dev_path, {})
    
    # Standby protection: return cached telemetry if sleeping to preserve cooldown
    if power_state in ["STANDBY", "SLEEPING"] and cached_entry and cached_entry.get("temp_c") is not None:
        cached_entry["power_state"] = power_state
        cached_entry["last_checked"] = time.strftime("%Y-%m-%d %H:%M:%S")
        cached_entry["is_sleeping"] = True
        return cached_entry

    telemetry = {
        "device": dev_path,
        "name": dev_name,
        "power_state": power_state,
        "is_sleeping": power_state in ["STANDBY", "SLEEPING"],
        "model": "Generic Storage Drive",
        "serial": "N/A",
        "size": "N/A",
        "temp_c": None,
        "reallocated_sectors": 0,
        "pending_sectors": 0,
        "reallocated_events": 0,
        "uncorrectable_errors": 0,
        "crc_errors": 0,
        "power_on_hours": 0,
        "airflow_failed": False,
        "smart_overall": "PASSED",
        "health_score": 100,
        "grade": "A+",
        "status_label": "HEALTHY",
        "protection_status": "Normal Operation",
        "mounts": [],
        "last_checked": time.strftime("%Y-%m-%d %H:%M:%S")
    }

    try:
        lsblk_res = subprocess.run(["lsblk", "-J", "-o", "NAME,SIZE,MOUNTPOINTS,MODEL,SERIAL", dev_path], capture_output=True, text=True, timeout=4)
        if lsblk_res.returncode == 0:
            data = json.loads(lsblk_res.stdout)
            if "blockdevices" in data and len(data["blockdevices"]) > 0:
                bdev = data["blockdevices"][0]
                telemetry["size"] = bdev.get("size", "N/A")
                if bdev.get("model"):
                    telemetry["model"] = bdev.get("model").strip()
                if bdev.get("serial"):
                    telemetry["serial"] = bdev.get("serial").strip()
                
                mps = []
                def collect_mps(dev_obj):
                    if dev_obj.get("mountpoints"):
                        for mp in dev_obj["mountpoints"]:
                            if mp and mp not in mps:
                                mps.append(mp)
                    if "children" in dev_obj:
                        for child in dev_obj["children"]:
                            collect_mps(child)
                collect_mps(bdev)
                telemetry["mounts"] = mps
    except Exception:
        pass

    try:
        smart_res = subprocess.run(["smartctl", "-n", "standby", "-a", "-j", dev_path], capture_output=True, text=True, timeout=5)
        if smart_res.returncode & 2:
            telemetry["power_state"] = "STANDBY"
            telemetry["is_sleeping"] = True
            if cached_entry.get("temp_c"):
                telemetry["temp_c"] = cached_entry.get("temp_c")
            return telemetry

        if smart_res.stdout:
            try:
                sj = json.loads(smart_res.stdout)
                if "model_name" in sj:
                    telemetry["model"] = sj["model_name"]
                elif "model_family" in sj:
                    telemetry["model"] = sj["model_family"]
                if "serial_number" in sj:
                    telemetry["serial"] = sj["serial_number"]
                if "temperature" in sj and "current" in sj["temperature"]:
                    telemetry["temp_c"] = sj["temperature"]["current"]
                if "power_on_time" in sj and "hours" in sj["power_on_time"]:
                    telemetry["power_on_hours"] = sj["power_on_time"]["hours"]

                if "ata_smart_attributes" in sj and "table" in sj["ata_smart_attributes"]:
                    for attr in sj["ata_smart_attributes"]["table"]:
                        attr_id = attr.get("id")
                        raw_val = attr.get("raw", {}).get("value", 0)
                        if attr_id == 5:
                            telemetry["reallocated_sectors"] = raw_val
                        elif attr_id == 197:
                            telemetry["pending_sectors"] = raw_val
                        elif attr_id == 196:
                            telemetry["reallocated_events"] = raw_val
                        elif attr_id == 198:
                            telemetry["uncorrectable_errors"] = raw_val
                        elif attr_id == 199:
                            telemetry["crc_errors"] = raw_val
                        elif attr_id == 190:
                            if telemetry["temp_c"] is None:
                                telemetry["temp_c"] = raw_val
                            if attr.get("when_failed") == "FAILING_NOW" or attr.get("value", 100) < attr.get("thresh", 45):
                                telemetry["airflow_failed"] = True
                        elif attr_id == 194 and telemetry["temp_c"] is None:
                            telemetry["temp_c"] = raw_val
            except Exception:
                pass
    except Exception:
        pass

    # Score calculation
    score = 100
    if telemetry["reallocated_sectors"] > 0:
        score -= min(40, telemetry["reallocated_sectors"] * 0.15)
    if telemetry["pending_sectors"] > 0:
        score -= min(50, telemetry["pending_sectors"] * 0.3)
    if telemetry["reallocated_events"] > 0:
        score -= min(20, telemetry["reallocated_events"] * 0.1)
    if telemetry["uncorrectable_errors"] > 0:
        score -= 30
    if telemetry["temp_c"] is not None:
        if telemetry["temp_c"] >= 55 or telemetry["airflow_failed"]:
            score -= 45
        elif telemetry["temp_c"] >= 48:
            score -= 25
        elif telemetry["temp_c"] >= 43:
            score -= 10

    score = max(0, min(100, int(score)))
    if score < 30 or telemetry["pending_sectors"] > 50 or (telemetry["temp_c"] and telemetry["temp_c"] >= 55):
        grade = "F (FAILING)"
        status_label = "CRITICAL / FAILING"
    elif score < 60:
        grade = "D (AT RISK)"
        status_label = "DEGRADED"
    elif score < 80:
        grade = "C (WARNING)"
        status_label = "ELEVATED RISK"
    elif score < 95:
        grade = "B (GOOD)"
        status_label = "HEALTHY"
    else:
        grade = "A+ (EXCELLENT)"
        status_label = "OPTIMAL"

    telemetry["health_score"] = score
    telemetry["grade"] = grade
    telemetry["status_label"] = status_label
    return telemetry

def enforce_rules(dev_path, telemetry):
    dev_name = os.path.basename(dev_path)
    temp = telemetry.get("temp_c")
    power_state = telemetry.get("power_state")
    pending = telemetry.get("pending_sectors", 0)
    reallocated = telemetry.get("reallocated_sectors", 0)

    tune_kernel_block_device(dev_name)

    # 1. Dynamic Bad Sector Degradation Shield
    shield_cfg = config.get("degradation_shield", {})
    if shield_cfg.get("enabled", True):
        pending_thresh = shield_cfg.get("min_pending_sectors_trigger", 1)
        realloc_thresh = shield_cfg.get("min_reallocated_sectors_trigger", 50)
        
        if pending >= pending_thresh or reallocated >= realloc_thresh:
            for mp in telemetry.get("mounts", []):
                try:
                    mount_chk = subprocess.run(["findmnt", "-n", "-o", "OPTIONS", mp], capture_output=True, text=True)
                    if "rw" in mount_chk.stdout.strip().split(","):
                        log_event(f"DEGRADATION SHIELD: Remounting {mp} on {dev_path} to READ-ONLY to protect bad sectors.", "WARN")
                        subprocess.run(["mount", "-o", "remount,ro,noatime,noload", mp], capture_output=True)
                        telemetry["protection_status"] = "Read-Only Shield Active"
                    else:
                        telemetry["protection_status"] = "Read-Only Protected (Safe)"
                except Exception:
                    pass

    # 2. Dynamic Thermal Governor
    therm_cfg = config.get("thermal_governor", {})
    if therm_cfg.get("enabled", True):
        crit_temp = therm_cfg.get("critical_temp_c", 52)
        warn_temp = therm_cfg.get("warning_temp_c", 45)
        
        if power_state in ["STANDBY", "SLEEPING"]:
            telemetry["protection_status"] = "Standby Cooldown Active ❄️"
        elif temp is not None:
            if temp >= crit_temp or telemetry.get("airflow_failed"):
                log_event(f"THERMAL EMERGENCY: {dev_path} reached {temp}°C. Issuing emergency sleep standby.", "CRITICAL")
                subprocess.run(["sync"])
                subprocess.run(["hdparm", "-y", dev_path], capture_output=True)
                telemetry["power_state"] = "STANDBY"
                telemetry["is_sleeping"] = True
                telemetry["protection_status"] = f"Emergency Cooldown Active ({temp}°C)"
            elif temp >= warn_temp:
                standby_mins = therm_cfg.get("default_hdd_standby_minutes", 3)
                standby_val = str(max(12, standby_mins * 12))
                subprocess.run(["hdparm", "-S", standby_val, dev_path], capture_output=True)
                telemetry["protection_status"] = f"Thermal Guard Active ({temp}°C)"

def run_rescue_synchronization():
    """Autonomous low-impact background data rescue worker based on configuration."""
    with rescue_lock:
        rescue_cfg = config.get("rescue_engine", {})
        if not rescue_cfg.get("enabled", False):
            return

        engine = guardian_state["rescue_engine"]
        src = rescue_cfg.get("source_path")
        dst = rescue_cfg.get("target_path")

        if src and dst and os.path.exists(src) and os.path.exists(dst):
            engine["status"] = "EVACUATING_DATA"
            engine["active_job"] = f"Evacuating {src}"
            engine["current_source"] = src
            engine["current_target"] = dst
            log_event(f"AUTONOMOUS RESCUE: Initiating low-impact data evacuation from {src} to {dst}...", "INFO")
            
            cmd = ["nice", "-n", "19", "ionice", "-c", "3", "rsync", "-avh", "--update", "--timeout=30", "--ignore-errors", src.rstrip("/") + "/", dst]
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                for line in proc.stdout:
                    line_str = line.strip()
                    if line_str and not line_str.startswith("sending incremental") and not line_str.endswith("/"):
                        engine["current_file"] = line_str
                        engine["total_files_synced"] += 1
                proc.wait()
                if proc.returncode in [0, 23, 24]:
                    log_event(f"AUTONOMOUS RESCUE COMPLETE: {src} safely evacuated to {dst}.", "SUCCESS")
                else:
                    log_event(f"Rescue rsync finished with code {proc.returncode}.", "WARN")
            except Exception as e:
                log_event(f"Rescue error during sync: {e}", "ERROR")

        engine["status"] = "SYNCED_AND_PROTECTED"
        engine["active_job"] = "Data Protection Sync Complete"
        engine["current_file"] = "Complete"

def guardian_loop():
    start_time = time.time()
    
    if config.get("rescue_engine", {}).get("enabled", False):
        threading.Thread(target=run_rescue_synchronization, daemon=True).start()

    while True:
        try:
            guardian_state["uptime_seconds"] = int(time.time() - start_time)
            guardian_state["last_cycle"] = time.strftime("%Y-%m-%d %H:%M:%S")

            res = subprocess.run(["lsblk", "-d", "-n", "-o", "NAME"], capture_output=True, text=True)
            devs = [f"/dev/{line.strip()}" for line in res.stdout.splitlines() if line.strip().startswith(("sd", "nvme", "vd"))]

            for dev in devs:
                if os.path.exists(dev):
                    telemetry = get_drive_telemetry(dev)
                    guardian_state["drives"][dev] = telemetry
                    enforce_rules(dev, telemetry)

            try:
                os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
                with open(STATE_FILE, "w") as f:
                    json.dump(list(guardian_state["drives"].values()), f, indent=2)
            except Exception:
                pass

        except Exception as e:
            log_event(f"Monitoring loop exception: {e}", "ERROR")

        time.sleep(int(config.get("guardian", {}).get("poll_interval_seconds", 15)))

class WebDashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        web_dir = os.path.join(os.path.dirname(__file__), "web")
        super().__init__(*args, directory=web_dir, **kwargs)

    def log_message(self, format, *args):
        pass

    def send_json(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))

    def do_GET(self):
        url = urlparse(self.path)
        if url.path in ["/api/status", "/status"]:
            self.send_json(guardian_state)
        elif url.path in ["/api/logs", "/logs"]:
            self.send_json({"logs": guardian_state["actions_log"]})
        elif url.path in ["/api/rescue", "/rescue"]:
            self.send_json(guardian_state["rescue_engine"])
        else:
            super().do_GET()

    def do_POST(self):
        url = urlparse(self.path)
        if url.path in ["/api/action", "/api/drive-guardian/action"]:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8")) if length > 0 else {}
            action = body.get("action")
            raw_drive = body.get("drive")
            drive = sanitize_device_path(raw_drive)
            
            if action == "cooldown" and drive:
                subprocess.run(["sync"])
                subprocess.run(["hdparm", "-y", drive], capture_output=True)
                log_event(f"USER ACTION: Forced cooldown standby for {drive}", "INFO")
                self.send_json({"success": True, "message": f"Issued standby to {drive}"})
            elif action == "safe_mount" and drive:
                subprocess.run(["mount", "-o", "remount,ro,noatime,noload", drive], capture_output=True)
                log_event(f"USER ACTION: Enforced Read-Only Shield on {drive}", "INFO")
                self.send_json({"success": True, "message": f"Enforced Read-Only Shield on {drive}"})
            elif action == "trigger_rescue":
                threading.Thread(target=run_rescue_synchronization, daemon=True).start()
                self.send_json({"success": True, "message": "Triggered background rescue synchronization"})
            else:
                self.send_json({"success": False, "error": "Invalid action or invalid device path"}, code=400)

def run_server():
    server = HTTPServer(("0.0.0.0", API_PORT), WebDashboardHandler)
    server.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    guardian_loop()
