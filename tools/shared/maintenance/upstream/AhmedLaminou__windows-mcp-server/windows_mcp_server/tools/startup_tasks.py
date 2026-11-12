import os
import subprocess
import winreg

from windows_mcp_server.registry import windows_mcp_tool


RUN_KEYS = [
    (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKCU"),
    (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run", "HKLM"),
]


def _run_powershell(script: str, timeout: int = 30) -> str:
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        return result.stderr.strip() or result.stdout.strip()
    return result.stdout.strip()


@windows_mcp_tool()
def get_startup_impact() -> str:
    """
    Combine startup registry entries, Startup folder shortcuts, and enabled scheduled tasks
    into one boot-impact report.
    """
    lines = ["Registry Run entries:"]
    for hive, key_path, hive_name in RUN_KEYS:
        try:
            with winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ) as key:
                for index in range(winreg.QueryInfoKey(key)[1]):
                    name, value, _ = winreg.EnumValue(key, index)
                    state = "Disabled" if name.startswith("Disabled_") else "Enabled"
                    lines.append(f"  [{hive_name}] {state}: {name} -> {value}")
        except FileNotFoundError:
            continue
        except Exception as exc:
            lines.append(f"  [{hive_name}] Error: {exc}")

    lines.append("\nStartup folder shortcuts:")
    startup_dirs = [
        os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup"),
        os.path.join(os.environ.get("PROGRAMDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup"),
    ]
    for folder in startup_dirs:
        if not folder or not os.path.exists(folder):
            continue
        for item in os.listdir(folder):
            state = "Disabled" if item.endswith(".disabled") else "Enabled"
            lines.append(f"  {state}: {os.path.join(folder, item)}")

    lines.append("\nEnabled scheduled startup/logon tasks:")
    script = (
        "Get-ScheduledTask | Where-Object { $_.State -ne 'Disabled' -and "
        "($_.Triggers -match 'Logon' -or $_.Triggers -match 'Startup') } | "
        "Select-Object TaskName,TaskPath,State | Format-Table -AutoSize | Out-String -Width 200"
    )
    tasks = _run_powershell(script)
    lines.append(tasks if tasks else "  None found.")

    return "\n".join(lines)


@windows_mcp_tool()
def list_scheduled_tasks(status: str = "all", max_tasks: int = 100) -> str:
    """
    List scheduled tasks with state, task path, last run, next run, and last result.
    Args:
        status: 'ready', 'running', 'disabled', or 'all'.
        max_tasks: Maximum number of tasks to return.
    """
    where = "" if status == "all" else f"| Where-Object State -eq '{status.capitalize()}'"
    script = (
        f"Get-ScheduledTask {where} | Select-Object -First {max_tasks} | ForEach-Object {{ "
        "$info = Get-ScheduledTaskInfo -TaskName $_.TaskName -TaskPath $_.TaskPath; "
        "[PSCustomObject]@{TaskName=$_.TaskName; TaskPath=$_.TaskPath; State=$_.State; "
        "LastRun=$info.LastRunTime; NextRun=$info.NextRunTime; LastResult=$info.LastTaskResult} "
        "} | Format-Table -AutoSize | Out-String -Width 220"
    )
    output = _run_powershell(script, timeout=60)
    return output or f"No scheduled tasks found for status '{status}'."


@windows_mcp_tool()
def enable_disable_startup_item(item_name: str, action: str, source: str = "registry") -> str:
    """
    Enable or disable a startup item.
    Args:
        item_name: Registry value name, scheduled task name, or Startup folder filename.
        action: 'enable' or 'disable'.
        source: 'registry', 'scheduled_task', or 'startup_folder'.
    """
    if action not in {"enable", "disable"}:
        return "Error: action must be 'enable' or 'disable'."

    if source == "scheduled_task":
        cmd = "Enable-ScheduledTask" if action == "enable" else "Disable-ScheduledTask"
        escaped_item_name = item_name.replace("'", "''")
        script = f"{cmd} -TaskName '{escaped_item_name}' | Out-String"
        return _run_powershell(script) or f"{action.capitalize()} requested for scheduled task '{item_name}'."

    if source == "registry":
        desired_prefix = "Disabled_"
        for hive, key_path, hive_name in RUN_KEYS:
            try:
                with winreg.OpenKey(hive, key_path, 0, winreg.KEY_ALL_ACCESS) as key:
                    source_name = f"{desired_prefix}{item_name}" if action == "enable" else item_name
                    target_name = item_name if action == "enable" else f"{desired_prefix}{item_name}"
                    value, value_type = winreg.QueryValueEx(key, source_name)
                    winreg.SetValueEx(key, target_name, 0, value_type, value)
                    winreg.DeleteValue(key, source_name)
                    return f"{action.capitalize()}d registry startup item '{item_name}' in {hive_name}."
            except FileNotFoundError:
                continue
            except PermissionError:
                return "Error: Access denied. Administrator privileges may be required."
            except Exception as exc:
                return f"Error updating registry startup item: {exc}"
        return f"Startup registry item '{item_name}' was not found."

    if source == "startup_folder":
        startup_dirs = [
            os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup"),
            os.path.join(os.environ.get("PROGRAMDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup"),
        ]
        for folder in startup_dirs:
            if not folder or not os.path.exists(folder):
                continue
            source_name = f"{item_name}.disabled" if action == "enable" else item_name
            target_name = item_name if action == "enable" else f"{item_name}.disabled"
            source_path = os.path.join(folder, source_name)
            target_path = os.path.join(folder, target_name)
            if os.path.exists(source_path):
                os.rename(source_path, target_path)
                return f"{action.capitalize()}d startup folder item '{item_name}'."
        return f"Startup folder item '{item_name}' was not found."

    return "Error: source must be 'registry', 'scheduled_task', or 'startup_folder'."
