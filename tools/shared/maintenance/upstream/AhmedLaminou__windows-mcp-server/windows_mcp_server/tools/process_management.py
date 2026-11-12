import psutil
import datetime
from windows_mcp_server.registry import windows_mcp_tool

@windows_mcp_tool()
def kill_process(pid: int = None, process_name: str = None) -> str:
    """
    Kill a Windows process by its exact PID or by its Name.
    WARNING: Use carefully, killing system processes may crash Windows.
    """
    if not pid and not process_name:
        return "Error: You must provide either pid or process_name."
        
    try:
        if pid:
            proc = psutil.Process(pid)
            name = proc.name()
            proc.kill()
            return f"Successfully killed process '{name}' (PID: {pid})"
        else:
            killed = []
            for p in psutil.process_iter(['pid', 'name']):
                if p.info['name'] and p.info['name'].lower() == process_name.lower():
                    p.kill()
                    killed.append(str(p.info['pid']))
            if killed:
                return f"Successfully killed processes named '{process_name}': PIDs {', '.join(killed)}"
            return f"No process found with name '{process_name}'"
    except psutil.NoSuchProcess:
        return "Error: No such process."
    except psutil.AccessDenied:
        return "Error: Access denied. Cannot kill process without Administrator privileges."
    except Exception as e:
        return f"Error: {str(e)}"

@windows_mcp_tool()
def suspend_process(pid: int) -> str:
    """Suspend (freeze) a running Windows process by its PID."""
    try:
        proc = psutil.Process(pid)
        proc.suspend()
        return f"Successfully suspended process '{proc.name()}' (PID: {pid})"
    except Exception as e:
        return f"Error suspending process: {str(e)}"

@windows_mcp_tool()
def resume_process(pid: int) -> str:
    """Resume (unfreeze) a suspended Windows process by its PID."""
    try:
        proc = psutil.Process(pid)
        proc.resume()
        return f"Successfully resumed process '{proc.name()}' (PID: {pid})"
    except Exception as e:
        return f"Error resuming process: {str(e)}"

@windows_mcp_tool()
def search_process_by_name(process_name: str) -> str:
    """Search for running processes containing a specific substring in their name."""
    matches = []
    for p in psutil.process_iter(['pid', 'name', 'username']):
        try:
            if p.info['name'] and process_name.lower() in p.info['name'].lower():
                matches.append(f"PID: {p.info['pid']} | Name: {p.info['name']} | User: {p.info['username']}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return "\n".join(matches) if matches else f"No processes found matching '{process_name}'."
