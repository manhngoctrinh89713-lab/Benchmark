"""System-Informations-Tools: CPU, Speicher, Disk, OS-Details"""
import subprocess
import platform
import os
from typing import Any


def _run(cmd: list[str], timeout: int = 10) -> str:
    """Führt einen Befehl sicher aus und gibt stdout zurück."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else result.stderr.strip()
    except subprocess.TimeoutExpired:
        return "Timeout: Befehl hat zu lange gedauert"
    except FileNotFoundError:
        return f"Befehl nicht gefunden: {cmd[0]}"
    except Exception as e:
        return f"Fehler: {str(e)}"


def get_system_info() -> dict[str, Any]:
    """Gibt allgemeine System-Informationen zurück: OS, Kernel, Uptime, Hostname."""
    hostname = _run(["hostname"])
    kernel = _run(["uname", "-r"])
    os_release = _run(["cat", "/etc/os-release"])
    uptime = _run(["uptime", "-p"])
    cpu_count = _run(["nproc"])
    arch = _run(["uname", "-m"])

    # CPU-Modell aus /proc/cpuinfo
    cpu_model = "unbekannt"
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if "model name" in line:
                    cpu_model = line.split(":")[1].strip()
                    break
    except Exception:
        pass

    # Arbeitsspeicher aus /proc/meminfo
    mem_total = "unbekannt"
    mem_available = "unbekannt"
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    mem_total = f"{kb // 1024} MB ({kb // 1048576} GB)"
                elif line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    mem_available = f"{kb // 1024} MB ({kb // 1048576} GB)"
    except Exception:
        pass

    return {
        "hostname": hostname,
        "kernel": kernel,
        "arch": arch,
        "uptime": uptime,
        "cpu_count": cpu_count,
        "cpu_model": cpu_model,
        "mem_total": mem_total,
        "mem_available": mem_available,
        "os_release": os_release,
    }


def get_disk_usage() -> dict[str, Any]:
    """Gibt Festplatten-Belegung aller gemounteten Laufwerke zurück."""
    output = _run(["df", "-h", "--output=source,size,used,avail,pcent,target"])
    lines = output.strip().split("\n")
    if not lines:
        return {"error": "Keine Disk-Daten verfügbar"}

    header = lines[0].split()
    disks = []
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 6:
            disks.append({
                "filesystem": parts[0],
                "size": parts[1],
                "used": parts[2],
                "available": parts[3],
                "use_pct": parts[4],
                "mountpoint": parts[5],
            })

    return {"disks": disks, "raw": output}


def get_memory_usage() -> dict[str, Any]:
    """Gibt detaillierte Speicher-Nutzung zurück (RAM + Swap)."""
    output = _run(["free", "-h"])
    mem_info = {}
    for line in output.split("\n"):
        if line.startswith("Mem:"):
            parts = line.split()
            mem_info["ram_total"] = parts[1]
            mem_info["ram_used"] = parts[2]
            mem_info["ram_free"] = parts[3]
            if len(parts) > 6:
                mem_info["ram_available"] = parts[6]
        elif line.startswith("Swap:"):
            parts = line.split()
            mem_info["swap_total"] = parts[1]
            mem_info["swap_used"] = parts[2]
            mem_info["swap_free"] = parts[3]
    return {"memory": mem_info, "raw": output}


def run_health_check() -> dict[str, Any]:
    """Führt einen vollständigen System-Health-Check durch."""
    checks = {}

    # Disk-Belegung über 80%?
    df_out = _run(["df", "-h", "--output=pcent,target"])
    high_disk = []
    for line in df_out.split("\n")[1:]:
        parts = line.strip().split()
        if len(parts) == 2:
            pct_str = parts[0].rstrip("%")
            try:
                if int(pct_str) >= 80:
                    high_disk.append({"mountpoint": parts[1], "usage": parts[0]})
            except ValueError:
                pass
    checks["disk_warnings"] = high_disk

    # Load Average
    load_out = _run(["cat", "/proc/loadavg"])
    parts = load_out.split()
    if len(parts) >= 3:
        checks["load_average"] = {
            "1min": parts[0],
            "5min": parts[1],
            "15min": parts[2],
        }

    # Speicher verfügbar
    mem_out = get_memory_usage()
    checks["memory"] = mem_out.get("memory", {})

    # Uptime
    checks["uptime"] = _run(["uptime", "-p"])

    # Hostname und Kernel
    checks["hostname"] = _run(["hostname"])
    checks["kernel"] = _run(["uname", "-r"])

    # Status-Bewertung
    issues = []
    if high_disk:
        issues.append(f"{len(high_disk)} Laufwerk(e) über 80% Belegung")
    try:
        load_1m = float(checks.get("load_average", {}).get("1min", "0"))
        cpu_count = int(_run(["nproc"]) or "1")
        if load_1m > cpu_count * 0.8:
            issues.append(f"Hohe CPU-Last: {load_1m} (bei {cpu_count} Kernen)")
    except (ValueError, TypeError):
        pass

    checks["status"] = "WARNING" if issues else "OK"
    checks["issues"] = issues

    return checks
