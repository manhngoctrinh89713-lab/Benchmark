import winreg
from windows_mcp_server.registry import windows_mcp_tool

@windows_mcp_tool()
def list_installed_software() -> str:
    """
    Retrieves a list of installed software from the Windows Registry,
    including the install date and estimated size if available.
    Use this to audit what software is installed and identify redundancy.
    """
    software_list = []
    
    # Registry paths where uninstall info is stored
    paths = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")
    ]
    
    for hkey, path in paths:
        try:
            with winreg.OpenKey(hkey, path) as key:
                for i in range(winreg.QueryInfoKey(key)[0]):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        with winreg.OpenKey(key, subkey_name) as subkey:
                            try:
                                name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                                
                                # Try to get size
                                try:
                                    size_kb = winreg.QueryValueEx(subkey, "EstimatedSize")[0]
                                    size_mb = size_kb / 1024
                                    size_str = f"{size_mb:.1f} MB"
                                except Exception:
                                    size_str = "Unknown Size"
                                    
                                # Try to get install date
                                try:
                                    date = winreg.QueryValueEx(subkey, "InstallDate")[0]
                                except Exception:
                                    date = "Unknown Date"
                                    
                                software_list.append((name, size_str, date))
                            except FileNotFoundError:
                                # Subkey doesn't have a DisplayName, skip it
                                pass
                    except OSError:
                        pass
        except FileNotFoundError:
            pass
            
    if not software_list:
        return "No software found or access denied to registry."
        
    # Sort alphabetically and remove duplicates
    software_list = sorted(list(set(software_list)), key=lambda x: x[0].lower())
    
    lines = [f"{'SOFTWARE NAME':<50} | {'SIZE':<15} | {'INSTALL DATE'}"]
    lines.append("-" * 85)
    for name, size, date in software_list:
        name_trunc = name[:47] + "..." if len(name) > 47 else name
        lines.append(f"{name_trunc:<50} | {size:<15} | {date}")
        
    return "\n".join(lines)
