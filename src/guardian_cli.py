#!/usr/bin/env python3
"""
Proxmox Drive Guardian CLI (Command-Line Utility)
================================================
Terminal interface to monitor and control the autonomous drive guardian.
Open-Source Community Edition (Zero Hardcoded Personal Data or Host Info)
"""

import sys
import os
import json
import urllib.request
import urllib.error

API_URL = "http://127.0.0.1:8095"

def get_json(endpoint):
    try:
        req = urllib.request.Request(f"{API_URL}{endpoint}")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        if endpoint in ["/api/status", "/status"] and os.path.exists("/var/lib/pve-drive-guardian/state.json"):
            try:
                with open("/var/lib/pve-drive-guardian/state.json", "r") as f:
                    data = json.load(f)
                    return {"drives": {d["device"]: d for d in data}, "rescue_engine": {}}
            except Exception:
                pass
        return None

def post_json(endpoint, payload):
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(f"{API_URL}{endpoint}", data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

def print_banner():
    print("\033[1;36m" + "=" * 76)
    print(" 🛡️  PROXMOX DRIVE GUARDIAN — STORAGE AI & THERMAL PROTECTION")
    print("=" * 76 + "\033[0m")

def show_status():
    print_banner()
    status_data = get_json("/api/status")
    if not status_data:
        print("\033[1;31m[-] Unable to communicate with Drive Guardian daemon (is pve-drive-guardian.service running?).\033[0m")
        sys.exit(1)

    drives = status_data.get("drives", {})
    rescue = status_data.get("rescue_engine", {})
    
    print(f"\033[1;32m● Daemon Status:\033[0m {status_data.get('status', 'ACTIVE')} (Uptime: {status_data.get('uptime_seconds', 0)}s) | \033[1;34mRescue Engine:\033[0m {rescue.get('status', 'IDLE')}")
    print("-" * 76)
    print(f"{'DEVICE':<10} {'MODEL':<24} {'TEMP':<12} {'POWER':<10} {'HEALTH':<16} {'PROTECTION':<14}")
    print("-" * 76)
    
    for dev, d in drives.items():
        dev_name = d.get("device", dev)
        model = (d.get("model") or "Generic Drive")[:22]
        temp = f"{d.get('temp_c')}°C" if d.get("temp_c") is not None else "STANDBY"
        if d.get("is_sleeping") or d.get("power_state") == "STANDBY":
            temp = "STANDBY ❄️"
        
        power = d.get("power_state", "ACTIVE")
        grade = d.get("grade", "A")
        reallocated = d.get("reallocated_sectors", 0)
        pending = d.get("pending_sectors", 0)
        
        if "FAIL" in grade or "CRIT" in d.get("status_label", ""):
            dev_str = f"\033[1;31m{dev_name}\033[0m"
            grade_str = f"\033[1;31m{grade}\033[0m"
        elif "DEGRAD" in grade or "WARN" in grade:
            dev_str = f"\033[1;33m{dev_name}\033[0m"
            grade_str = f"\033[1;33m{grade}\033[0m"
        else:
            dev_str = f"\033[1;32m{dev_name}\033[0m"
            grade_str = f"\033[1;32m{grade}\033[0m"

        if d.get("temp_c") and d.get("temp_c") >= 50:
            temp_str = f"\033[1;31m{temp}\033[0m"
        elif d.get("temp_c") and d.get("temp_c") >= 44:
            temp_str = f"\033[1;33m{temp}\033[0m"
        else:
            temp_str = f"\033[1;36m{temp}\033[0m"

        status_text = d.get("protection_status", "Normal Operation")
        print(f"{dev_str:<19} {model:<24} {temp_str:<21} {power:<10} {grade_str:<25} {status_text}")
        
        if pending > 0 or reallocated > 0:
            print(f"  \033[1;33m↳ Degradation:\033[0m {reallocated} Reallocated Sectors | {pending} Pending Sectors")

    print("-" * 76)
    if rescue and rescue.get("active_job"):
        print(f"\033[1;33m🔄 Active Rescue Job:\033[0m {rescue.get('active_job')}")
        print(f"   \033[1;37mSource:\033[0m {rescue.get('current_source')} ➜ \033[1;37mTarget:\033[0m {rescue.get('current_target')}")
        print(f"   \033[1;37mCurrent File:\033[0m {rescue.get('current_file', 'Synchronizing...')}")
        print(f"   \033[1;37mFiles Synced:\033[0m {rescue.get('total_files_synced', 0)} | Errors: {rescue.get('errors_count', 0)}")
    print("\033[1;36m" + "=" * 76 + "\033[0m\n")

def show_rescue():
    rescue = get_json("/api/rescue")
    if not rescue:
        print("No active rescue telemetry available.")
        return
    print("\033[1;33m=== DATA RESCUE & MIRRORING STATUS ===\033[0m")
    print(json.dumps(rescue, indent=2))

def trigger_cooldown(target):
    if not target:
        print("Usage: drive-guardian cool /dev/sdX")
        return
    print(f"\033[1;34m[*] Requesting emergency standby/cooldown for {target}...\033[0m")
    res = post_json("/api/action", {"action": "cooldown", "drive": target})
    print(f"\033[1;32m[+] Response: {res}\033[0m")

def trigger_rescue():
    print("\033[1;34m[*] Triggering rescue synchronization...\033[0m")
    res = post_json("/api/action", {"action": "trigger_rescue"})
    print(f"\033[1;32m[+] Response: {res}\033[0m")

def show_logs():
    logs_data = get_json("/api/logs")
    if not logs_data or "logs" not in logs_data:
        print("No recent log events found.")
        return
    print("\033[1;36m=== PROXMOX DRIVE GUARDIAN ACTIONS LOG (LATEST 30) ===\033[0m")
    for item in logs_data["logs"][:30]:
        lvl = item.get("level", "INFO")
        col = "\033[1;32m" if lvl == "SUCCESS" else "\033[1;31m" if lvl in ["CRITICAL", "ERROR"] else "\033[1;33m" if lvl == "WARN" else "\033[0m"
        print(f"{col}[{item.get('time')}] [{lvl}] {item.get('message')}\033[0m")

def main():
    if len(sys.argv) < 2:
        show_status()
        print("Commands: status | rescue | cool <dev> | trigger-rescue | logs")
        return

    cmd = sys.argv[1].lower()
    if cmd in ["status", "s", "-s"]:
        show_status()
    elif cmd in ["rescue", "r", "sync"]:
        show_rescue()
    elif cmd in ["cool", "sleep", "standby"]:
        target = sys.argv[2] if len(sys.argv) > 2 else ""
        trigger_cooldown(target)
    elif cmd in ["trigger-rescue", "start-rescue"]:
        trigger_rescue()
    elif cmd in ["logs", "log", "l"]:
        show_logs()
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: drive-guardian [status|rescue|cool <dev>|trigger-rescue|logs]")

if __name__ == "__main__":
    main()
