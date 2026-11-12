"""Systemd-Service-Management-Tools: Status, Start, Stop, Restart"""
import subprocess
from typing import Any


def _run(cmd: list[str], timeout: int = 15) -> tuple[int, str, str]:
    """Führt einen Befehl aus und gibt (returncode, stdout, stderr) zurück."""
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
        return 1, "", "Timeout: Befehl hat zu lange gedauert"
    except FileNotFoundError:
        return 1, "", f"Befehl nicht gefunden: {cmd[0]}"
    except Exception as e:
        return 1, "", str(e)


def list_services(filter_state: str = "all") -> dict[str, Any]:
    """
    Listet systemd-Services auf.
    filter_state: 'all', 'running', 'failed', 'inactive'
    """
    cmd = ["systemctl", "list-units", "--type=service", "--no-pager", "--plain"]
    if filter_state == "running":
        cmd.extend(["--state=running"])
    elif filter_state == "failed":
        cmd.extend(["--state=failed"])
    elif filter_state == "inactive":
        cmd.extend(["--state=inactive"])

    rc, stdout, stderr = _run(cmd)
    if rc != 0:
        return {"error": stderr or "systemctl nicht verfügbar", "services": []}

    services = []
    for line in stdout.split("\n"):
        parts = line.split(None, 4)
        if len(parts) >= 4 and parts[0].endswith(".service"):
            services.append({
                "name": parts[0],
                "load": parts[1],
                "active": parts[2],
                "sub": parts[3],
                "description": parts[4].strip() if len(parts) > 4 else "",
            })

    return {
        "filter": filter_state,
        "count": len(services),
        "services": services[:50],  # Max 50 zurückgeben
    }


def get_service_status(service_name: str) -> dict[str, Any]:
    """Gibt detaillierten Status eines systemd-Services zurück."""
    # Sicherheitscheck: Service-Name darf keine Shell-Sonderzeichen enthalten
    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    if not all(c in safe_chars for c in service_name):
        return {"error": f"Ungültiger Service-Name: {service_name}"}

    # .service anhängen falls nicht vorhanden
    if not service_name.endswith(".service"):
        service_name = service_name + ".service"

    rc, stdout, stderr = _run(["systemctl", "status", service_name, "--no-pager", "-l"])

    # Is-active und Is-enabled abfragen
    _, active_out, _ = _run(["systemctl", "is-active", service_name])
    _, enabled_out, _ = _run(["systemctl", "is-enabled", service_name])

    return {
        "service": service_name,
        "active": active_out,
        "enabled": enabled_out,
        "status_output": stdout if stdout else stderr,
        "exit_code": rc,
    }


def manage_service(service_name: str, action: str) -> dict[str, Any]:
    """
    Verwaltet einen systemd-Service.
    action: 'start', 'stop', 'restart', 'reload', 'enable', 'disable'

    HINWEIS: Benötigt sudo-Rechte für start/stop/restart/enable/disable.
    """
    # Sicherheitscheck
    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    if not all(c in safe_chars for c in service_name):
        return {"error": f"Ungültiger Service-Name: {service_name}"}

    allowed_actions = {"start", "stop", "restart", "reload", "enable", "disable"}
    if action not in allowed_actions:
        return {"error": f"Ungültige Aktion. Erlaubt: {', '.join(allowed_actions)}"}

    if not service_name.endswith(".service"):
        service_name = service_name + ".service"

    rc, stdout, stderr = _run(["systemctl", action, service_name])

    if rc == 0:
        # Nach Statusänderung den neuen Status abrufen
        _, active_out, _ = _run(["systemctl", "is-active", service_name])
        return {
            "success": True,
            "service": service_name,
            "action": action,
            "new_state": active_out,
            "message": f"Service {service_name} erfolgreich: {action}",
        }
    else:
        return {
            "success": False,
            "service": service_name,
            "action": action,
            "error": stderr or stdout,
        }


def get_service_logs(service_name: str, lines: int = 50) -> dict[str, Any]:
    """Gibt die letzten Log-Zeilen eines Services über journalctl zurück."""
    safe_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
    if not all(c in safe_chars for c in service_name):
        return {"error": f"Ungültiger Service-Name: {service_name}"}

    if not service_name.endswith(".service"):
        service_name = service_name + ".service"

    lines = min(max(1, lines), 500)  # Zwischen 1 und 500

    rc, stdout, stderr = _run(
        ["journalctl", "-u", service_name, "-n", str(lines), "--no-pager", "--output=short"],
        timeout=20,
    )

    return {
        "service": service_name,
        "lines_requested": lines,
        "logs": stdout if stdout else stderr,
        "success": rc == 0,
    }
