"""Prozess-Management-Tools: Laufende Prozesse, Top-Verbraucher, Suche"""
import subprocess
from typing import Any


def _run(cmd: list[str], timeout: int = 10) -> tuple[int, str, str]:
    """Führt einen Befehl sicher aus."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, "", "Timeout"
    except FileNotFoundError:
        return 1, "", f"Befehl nicht gefunden: {cmd[0]}"
    except Exception as e:
        return 1, "", str(e)


def list_processes(sort_by: str = "cpu", limit: int = 20) -> dict[str, Any]:
    """
    Listet laufende Prozesse auf.
    sort_by: 'cpu', 'memory', 'pid'
    limit: Anzahl der zurückgegebenen Prozesse (max 100)
    """
    limit = min(max(1, limit), 100)

    # Sortier-Option festlegen
    sort_map = {
        "cpu": "-k3",
        "memory": "-k4",
        "pid": "-k1",
    }
    sort_flag = sort_map.get(sort_by, "-k3")

    rc, stdout, stderr = _run([
        "ps", "aux", "--no-headers"
    ])

    if rc != 0:
        return {"error": stderr, "processes": []}

    processes = []
    lines = stdout.split("\n")

    # Nach CPU oder Memory sortieren
    def sort_key(line):
        parts = line.split(None, 10)
        if len(parts) < 4:
            return 0.0
        try:
            if sort_by == "memory":
                return float(parts[3])
            elif sort_by == "pid":
                return int(parts[1])
            else:  # cpu
                return float(parts[2])
        except ValueError:
            return 0.0

    lines.sort(key=sort_key, reverse=(sort_by != "pid"))

    for line in lines[:limit]:
        parts = line.split(None, 10)
        if len(parts) >= 11:
            processes.append({
                "user": parts[0],
                "pid": parts[1],
                "cpu_pct": parts[2],
                "mem_pct": parts[3],
                "vsz": parts[4],
                "rss": parts[5],
                "stat": parts[7],
                "start": parts[8],
                "time": parts[9],
                "command": parts[10][:100],  # Befehl kürzen
            })

    return {
        "sort_by": sort_by,
        "count": len(processes),
        "processes": processes,
    }


def find_process(name: str) -> dict[str, Any]:
    """Sucht nach Prozessen mit einem bestimmten Namen."""
    # Sicherheitscheck: Name darf keine Shell-Sonderzeichen enthalten
    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_. /")
    if not all(c in safe_chars for c in name):
        return {"error": f"Ungültiger Prozessname: {name}"}

    rc, stdout, stderr = _run(["pgrep", "-a", "-f", name])

    processes = []
    if rc == 0 and stdout:
        for line in stdout.split("\n"):
            parts = line.split(None, 1)
            if len(parts) == 2:
                processes.append({"pid": parts[0], "command": parts[1]})

    return {
        "search": name,
        "found": len(processes),
        "processes": processes,
    }


def get_top_consumers() -> dict[str, Any]:
    """Gibt die Top-5 CPU- und Memory-Verbraucher zurück."""
    rc, stdout, _ = _run(["ps", "aux", "--no-headers"])
    if rc != 0:
        return {"error": "ps nicht verfügbar"}

    lines = [l for l in stdout.split("\n") if l.strip()]

    def parse_line(line: str) -> dict:
        parts = line.split(None, 10)
        if len(parts) < 11:
            return {}
        return {
            "user": parts[0],
            "pid": parts[1],
            "cpu_pct": parts[2],
            "mem_pct": parts[3],
            "command": parts[10][:80],
        }

    # CPU-Verbraucher
    try:
        cpu_sorted = sorted(lines, key=lambda l: float(l.split(None, 3)[2]), reverse=True)
        top_cpu = [parse_line(l) for l in cpu_sorted[:5] if parse_line(l)]
    except (IndexError, ValueError):
        top_cpu = []

    # Memory-Verbraucher
    try:
        mem_sorted = sorted(lines, key=lambda l: float(l.split(None, 4)[3]), reverse=True)
        top_mem = [parse_line(l) for l in mem_sorted[:5] if parse_line(l)]
    except (IndexError, ValueError):
        top_mem = []

    return {
        "top_cpu": top_cpu,
        "top_memory": top_mem,
    }
