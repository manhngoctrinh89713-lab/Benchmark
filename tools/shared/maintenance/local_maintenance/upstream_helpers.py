"""Extracted helpers; attribution and changes are in EXTRACTION.json and NOTICE."""
from pydantic import BaseModel

class ProcessInfo(BaseModel):
    """Parsed process information from ps output."""

    pid: int
    user: str
    cpu_percent: float
    mem_percent: float
    vsz: int
    rss: int
    tty: str
    stat: str
    start: str
    time: str
    command: str


def parse_ps_output(stdout: str) -> list[ProcessInfo]:
    """Parse ps aux output into ProcessInfo objects.

    Args:
        stdout: Raw output from ps aux command.

    Returns:
        List of ProcessInfo objects.
    """
    processes = []
    lines = stdout.strip().split("\n")

    # Skip header line
    for line in lines[1:]:
        parts = line.split(None, 10)  # Split into max 11 parts
        if len(parts) < 11:
            continue

        try:
            processes.append(
                ProcessInfo(
                    user=parts[0],
                    pid=int(parts[1]),
                    cpu_percent=float(parts[2]),
                    mem_percent=float(parts[3]),
                    vsz=int(parts[4]),
                    rss=int(parts[5]),
                    tty=parts[6],
                    stat=parts[7],
                    start=parts[8],
                    time=parts[9],
                    command=parts[10] if len(parts) > 10 else "",
                )
            )
        except ValueError:
            # Silently skip invalid process lines
            continue

    return processes


def format_bytes(bytes_value: int | float) -> str:
    """
    Format bytes into human-readable format.

    Args:
        bytes_value: Number of bytes to format

    Returns:
        Human-readable string representation (e.g., "1.5GB", "256.0MB")

    Examples:
        >>> format_bytes(1024)
        '1.0KB'
        >>> format_bytes(1536)
        '1.5KB'
        >>> format_bytes(1073741824)
        '1.0GB'
    """
    value = float(bytes_value)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024.0:
            return f"{value:.1f}{unit}"

        value /= 1024.0

    return f"{value:.1f}PB"


def filter_windows_processes(process_name: str, processes: list[dict]) -> list[dict]:
    matches = []
    for info in processes:
        if info['name'] and process_name.lower() in info['name'].lower():
            matches.append(info)
    return matches
