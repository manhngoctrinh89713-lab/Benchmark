import subprocess
import winreg

from windows_mcp_server.registry import windows_mcp_tool


UNINSTALL_PATHS = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "HKLM32"),
    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "HKCU"),
]


def _read_value(key, name: str) -> str:
    try:
        return str(winreg.QueryValueEx(key, name)[0])
    except Exception:
        return ""


def _uninstall_entries() -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for hive, path, hive_name in UNINSTALL_PATHS:
        try:
            with winreg.OpenKey(hive, path) as key:
                for index in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        subkey_name = winreg.EnumKey(key, index)
                        with winreg.OpenKey(key, subkey_name) as subkey:
                            display_name = _read_value(subkey, "DisplayName")
                            if not display_name:
                                continue
                            entries.append({
                                "name": display_name,
                                "version": _read_value(subkey, "DisplayVersion"),
                                "publisher": _read_value(subkey, "Publisher"),
                                "install_location": _read_value(subkey, "InstallLocation"),
                                "uninstall": _read_value(subkey, "UninstallString"),
                                "quiet_uninstall": _read_value(subkey, "QuietUninstallString"),
                                "registry": f"{hive_name}\\{path}\\{subkey_name}",
                            })
                    except OSError:
                        continue
        except FileNotFoundError:
            continue
    return entries


@windows_mcp_tool()
def find_uninstall_entries(query: str = "", limit: int = 50) -> str:
    """
    Search installed software uninstall entries, including uninstall commands.
    """
    query_lower = query.lower()
    matches = [
        entry for entry in _uninstall_entries()
        if not query_lower or query_lower in entry["name"].lower()
    ]
    matches.sort(key=lambda item: item["name"].lower())

    if not matches:
        return f"No uninstall entries found matching '{query}'."

    lines: list[str] = []
    for entry in matches[:limit]:
        lines.extend([
            f"Name: {entry['name']}",
            f"  Version: {entry['version'] or 'Unknown'}",
            f"  Publisher: {entry['publisher'] or 'Unknown'}",
            f"  Install Location: {entry['install_location'] or 'Unknown'}",
            f"  Registry: {entry['registry']}",
            f"  Uninstall: {entry['uninstall'] or 'Unavailable'}",
            f"  Quiet Uninstall: {entry['quiet_uninstall'] or 'Unavailable'}",
            "",
        ])
    if len(matches) > limit:
        lines.append(f"... and {len(matches) - limit} more matches.")
    return "\n".join(lines).rstrip()


@windows_mcp_tool()
def uninstall_software(query: str, dry_run: bool = True, prefer_quiet: bool = True) -> str:
    """
    Preview or launch an installed software uninstaller.
    Args:
        query: Case-insensitive substring matched against DisplayName. Must match exactly one entry.
        dry_run: Defaults to true; returns the uninstall command without running it.
        prefer_quiet: Use QuietUninstallString when available.
    """
    query_lower = query.lower()
    matches = [entry for entry in _uninstall_entries() if query_lower in entry["name"].lower()]
    if not matches:
        return f"No uninstall entry found matching '{query}'."
    if len(matches) > 1:
        names = "\n".join(f"  {entry['name']}" for entry in matches[:20])
        return f"Query matched {len(matches)} entries. Narrow it down before uninstalling:\n{names}"

    entry = matches[0]
    command = entry["quiet_uninstall"] if prefer_quiet and entry["quiet_uninstall"] else entry["uninstall"]
    if not command:
        return f"No uninstall command is available for '{entry['name']}'."

    if dry_run:
        return (
            f"Dry run. Would uninstall '{entry['name']}'.\n"
            f"Command: {command}\n"
            "Run again with dry_run=false only after confirming this is the intended app."
        )

    escaped_command = command.replace("'", "''")
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", f"Start-Process -FilePath 'cmd.exe' -ArgumentList '/c {escaped_command}' -Wait"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return result.stderr.strip() or f"Uninstaller returned exit code {result.returncode}."
    return f"Uninstaller launched for '{entry['name']}'."
