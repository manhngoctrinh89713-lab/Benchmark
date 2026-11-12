import os
import time
import datetime
from windows_mcp_server.registry import windows_mcp_tool

def _format_size(size_bytes: int) -> str:
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = int(os.math.floor(os.math.log(size_bytes, 1024))) if hasattr(os, 'math') else 0
    # Manual log base 1024
    temp = size_bytes
    idx = 0
    while temp >= 1024 and idx < len(size_name) - 1:
        temp /= 1024
        idx += 1
    return f"{temp:.2f} {size_name[idx]}"

@windows_mcp_tool()
def analyze_directory_space(directory_path: str, top_n: int = 20) -> str:
    """
    Analyze a directory to find the largest files and subdirectories.
    Useful for freeing up disk space.
    
    Args:
        directory_path: Absolute path to the directory to analyze (e.g. 'C:\\Users\\name\\Downloads').
        top_n: Number of largest items to return.
    """
    if not os.path.exists(directory_path):
        return f"Error: Directory '{directory_path}' does not exist."
        
    items = []
    
    try:
        for entry in os.scandir(directory_path):
            try:
                if entry.is_file(follow_symlinks=False):
                    size = entry.stat(follow_symlinks=False).st_size
                    items.append({"name": entry.name, "type": "File", "size": size})
                elif entry.is_dir(follow_symlinks=False):
                    # For directories, just get their immediate size or 0 if we don't do deep scan
                    # A deep scan is too slow for large drives, so we only measure files in this directory.
                    # To be helpful, we can recursively size it but we limit depth or just report top level.
                    dir_size = 0
                    for dirpath, _, filenames in os.walk(entry.path):
                        for f in filenames:
                            try:
                                fp = os.path.join(dirpath, f)
                                if not os.path.islink(fp):
                                    dir_size += os.path.getsize(fp)
                            except Exception:
                                pass
                    items.append({"name": entry.name, "type": "Folder", "size": dir_size})
            except Exception:
                pass
    except PermissionError:
        return f"Error: Permission denied accessing '{directory_path}'."
        
    items.sort(key=lambda x: x["size"], reverse=True)
    
    lines = [f"Analysis of: {directory_path}", ""]
    lines.append(f"{'TYPE':<8} | {'NAME':<50} | {'SIZE'}")
    lines.append("-" * 75)
    for item in items[:top_n]:
        name_trunc = item['name'][:47] + "..." if len(item['name']) > 47 else item['name']
        size_str = _format_size(item['size'])
        lines.append(f"{item['type']:<8} | {name_trunc:<50} | {size_str}")
        
    return "\n".join(lines)

@windows_mcp_tool()
def find_unused_files(directory_path: str, days_unused: int = 90, limit: int = 50) -> str:
    """
    Find files in a directory that haven't been accessed or modified in a long time.
    Use this to identify useless or forgotten files taking up space.
    
    Args:
        directory_path: Path to scan.
        days_unused: Threshold in days (e.g. 90 days).
        limit: Max number of files to return.
    """
    if not os.path.exists(directory_path):
        return f"Error: Directory '{directory_path}' does not exist."
        
    current_time = time.time()
    threshold_time = current_time - (days_unused * 86400)
    
    unused_files = []
    
    try:
        for dirpath, _, filenames in os.walk(directory_path):
            for f in filenames:
                try:
                    fp = os.path.join(dirpath, f)
                    if not os.path.islink(fp):
                        stat = os.stat(fp)
                        # Check last access (atime) and last modified (mtime)
                        if stat.st_atime < threshold_time and stat.st_mtime < threshold_time:
                            unused_files.append({
                                "path": fp,
                                "size": stat.st_size,
                                "last_access": datetime.datetime.fromtimestamp(stat.st_atime).strftime('%Y-%m-%d')
                            })
                except Exception:
                    pass
    except Exception as e:
        return f"Error during scan: {str(e)}"
        
    # Sort by size to show biggest wasted space first
    unused_files.sort(key=lambda x: x["size"], reverse=True)
    
    if not unused_files:
        return f"No files found unused for more than {days_unused} days."
        
    lines = [f"Unused files in '{directory_path}' (>{days_unused} days):", ""]
    lines.append(f"{'SIZE':<15} | {'LAST ACCESSED':<15} | {'FILE PATH'}")
    lines.append("-" * 90)
    for f in unused_files[:limit]:
        size_str = _format_size(f['size'])
        lines.append(f"{size_str:<15} | {f['last_access']:<15} | {f['path']}")
        
    return "\n".join(lines)
