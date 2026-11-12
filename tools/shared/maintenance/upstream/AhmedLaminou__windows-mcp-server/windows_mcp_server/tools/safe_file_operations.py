import datetime
import glob
import hashlib
import os
import shutil
import subprocess
import zipfile

from windows_mcp_server.registry import windows_mcp_tool


def _format_size(size_bytes: int) -> str:
    if size_bytes == 0:
        return "0B"
    names = ("B", "KB", "MB", "GB", "TB")
    size = float(size_bytes)
    index = 0
    while size >= 1024 and index < len(names) - 1:
        size /= 1024
        index += 1
    return f"{size:.2f} {names[index]}"


def _hash_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@windows_mcp_tool()
def find_large_duplicates(directory_path: str, min_size_mb: float = 25.0, limit: int = 50) -> str:
    """
    Find likely duplicate large files by size, then confirm duplicates with SHA-256 hashes.
    """
    if not os.path.exists(directory_path):
        return f"Error: Directory '{directory_path}' does not exist."

    min_size = int(min_size_mb * 1024 * 1024)
    by_size: dict[int, list[str]] = {}
    for root, _, files in os.walk(directory_path):
        for filename in files:
            path = os.path.join(root, filename)
            try:
                if not os.path.islink(path):
                    size = os.path.getsize(path)
                    if size >= min_size:
                        by_size.setdefault(size, []).append(path)
            except Exception:
                continue

    duplicates: dict[str, list[str]] = {}
    for size, paths in by_size.items():
        if len(paths) < 2:
            continue
        for path in paths:
            try:
                duplicates.setdefault(_hash_file(path), []).append(path)
            except Exception:
                continue

    groups = [paths for paths in duplicates.values() if len(paths) > 1]
    if not groups:
        return f"No duplicate files larger than {min_size_mb} MB found in '{directory_path}'."

    lines: list[str] = []
    for group_index, paths in enumerate(groups[:limit], start=1):
        size = os.path.getsize(paths[0])
        lines.append(f"Duplicate group {group_index}: {len(paths)} files, {_format_size(size)} each")
        lines.extend(f"  {path}" for path in paths)
    return "\n".join(lines)


@windows_mcp_tool()
def safe_delete_to_recycle_bin(file_path: str) -> str:
    """
    Delete a file or folder through the Windows Recycle Bin instead of permanent deletion.
    """
    if not os.path.exists(file_path):
        return f"Error: Path '{file_path}' does not exist."

    escaped = file_path.replace("'", "''")
    script = (
        "Add-Type -AssemblyName Microsoft.VisualBasic; "
        f"[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile('{escaped}', "
        "[Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs, "
        "[Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin)"
    )
    if os.path.isdir(file_path):
        script = (
            "Add-Type -AssemblyName Microsoft.VisualBasic; "
            f"[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory('{escaped}', "
            "[Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs, "
            "[Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin)"
        )

    result = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True)
    if result.returncode != 0:
        return result.stderr.strip() or f"Error sending '{file_path}' to Recycle Bin."
    return f"Sent '{file_path}' to the Recycle Bin."


@windows_mcp_tool()
def safe_delete_many_to_recycle_bin(paths: str, dry_run: bool = False, limit: int = 100) -> str:
    """
    Send multiple files or folders to the Windows Recycle Bin.
    Args:
        paths: Newline-separated paths.
        dry_run: If true, only preview what would be deleted.
        limit: Maximum number of paths to process.
    """
    requested_paths = [path.strip().strip('"') for path in paths.splitlines() if path.strip()]
    if not requested_paths:
        return "Error: provide one or more newline-separated paths."

    existing_paths = [path for path in requested_paths if os.path.exists(path)]
    missing_paths = [path for path in requested_paths if not os.path.exists(path)]
    selected_paths = existing_paths[:limit]

    lines = [
        f"Requested: {len(requested_paths)} path(s)",
        f"Existing: {len(existing_paths)}",
        f"Missing: {len(missing_paths)}",
    ]

    if missing_paths:
        lines.append("\nMissing paths:")
        lines.extend(f"  {path}" for path in missing_paths[:20])
        if len(missing_paths) > 20:
            lines.append(f"  ... and {len(missing_paths) - 20} more")

    if dry_run:
        lines.append("\nDry run. Would send to Recycle Bin:")
        lines.extend(f"  {path}" for path in selected_paths)
        if len(existing_paths) > limit:
            lines.append(f"  ... and {len(existing_paths) - limit} more skipped by limit")
        return "\n".join(lines)

    deleted = 0
    errors: list[str] = []
    for path in selected_paths:
        result = safe_delete_to_recycle_bin(path)
        if result.startswith("Sent "):
            deleted += 1
        else:
            errors.append(f"{path}: {result}")

    lines.append(f"\nSent to Recycle Bin: {deleted}")
    if len(existing_paths) > limit:
        lines.append(f"Skipped by limit: {len(existing_paths) - limit}")
    if errors:
        lines.append("\nErrors:")
        lines.extend(f"  {error}" for error in errors[:20])
        if len(errors) > 20:
            lines.append(f"  ... and {len(errors) - 20} more")
    return "\n".join(lines)


@windows_mcp_tool()
def safe_delete_by_pattern(
    directory_path: str,
    pattern: str,
    recursive: bool = False,
    dry_run: bool = True,
    limit: int = 100,
) -> str:
    """
    Find files matching a glob pattern and optionally send them to the Recycle Bin.
    Args:
        directory_path: Folder to search.
        pattern: Glob pattern such as '*.log', '*.tmp', or 'build-*'.
        recursive: Search subfolders when true.
        dry_run: Defaults to true so pattern matches can be reviewed before deleting.
        limit: Maximum number of matched paths to process.
    """
    if not os.path.isdir(directory_path):
        return f"Error: Directory '{directory_path}' does not exist."
    if not pattern or os.path.isabs(pattern):
        return "Error: pattern must be a relative glob pattern like '*.log' or 'cache-*'."

    search_root = os.path.abspath(directory_path)
    search_pattern = os.path.join(search_root, "**", pattern) if recursive else os.path.join(search_root, pattern)
    matches = [
        path for path in glob.glob(search_pattern, recursive=recursive)
        if os.path.abspath(path).startswith(search_root) and os.path.exists(path)
    ]
    matches.sort()

    if not matches:
        return f"No matches found for pattern '{pattern}' in '{directory_path}'."

    total_bytes = 0
    for path in matches:
        try:
            if os.path.isfile(path):
                total_bytes += os.path.getsize(path)
        except Exception:
            continue

    lines = [
        f"Pattern: {pattern}",
        f"Directory: {search_root}",
        f"Recursive: {recursive}",
        f"Matches: {len(matches)}",
        f"Matched file bytes: {_format_size(total_bytes)}",
    ]

    selected = matches[:limit]
    if dry_run:
        lines.append("\nDry run. Would send to Recycle Bin:")
        lines.extend(f"  {path}" for path in selected)
        if len(matches) > limit:
            lines.append(f"  ... and {len(matches) - limit} more skipped by limit")
        return "\n".join(lines)

    deleted = 0
    errors: list[str] = []
    for path in selected:
        result = safe_delete_to_recycle_bin(path)
        if result.startswith("Sent "):
            deleted += 1
        else:
            errors.append(f"{path}: {result}")

    lines.append(f"\nSent to Recycle Bin: {deleted}")
    if len(matches) > limit:
        lines.append(f"Skipped by limit: {len(matches) - limit}")
    if errors:
        lines.append("\nErrors:")
        lines.extend(f"  {error}" for error in errors[:20])
        if len(errors) > 20:
            lines.append(f"  ... and {len(errors) - 20} more")
    return "\n".join(lines)


@windows_mcp_tool()
def compress_old_files(
    directory_path: str,
    days_old: int = 90,
    archive_path: str = "",
    delete_after: bool = False,
    limit: int = 500,
) -> str:
    """
    Archive files older than a threshold into a zip file.
    Args:
        directory_path: Directory to scan recursively.
        days_old: Include files last modified before this many days.
        archive_path: Optional zip path. Defaults inside directory_path.
        delete_after: Delete archived originals after zip creation.
        limit: Maximum number of files to archive.
    """
    if not os.path.isdir(directory_path):
        return f"Error: Directory '{directory_path}' does not exist."

    cutoff = datetime.datetime.now().timestamp() - (days_old * 86400)
    archive_path = archive_path or os.path.join(
        directory_path,
        f"old-files-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.zip",
    )

    candidates: list[str] = []
    for root, _, files in os.walk(directory_path):
        for filename in files:
            path = os.path.join(root, filename)
            if os.path.abspath(path) == os.path.abspath(archive_path):
                continue
            try:
                if os.path.getmtime(path) < cutoff:
                    candidates.append(path)
            except Exception:
                continue
            if len(candidates) >= limit:
                break
        if len(candidates) >= limit:
            break

    if not candidates:
        return f"No files older than {days_old} days found in '{directory_path}'."

    archived = 0
    errors = 0
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in candidates:
            try:
                archive.write(path, os.path.relpath(path, directory_path))
                archived += 1
                if delete_after:
                    os.remove(path)
            except Exception:
                errors += 1

    return f"Archived {archived} old files to '{archive_path}'. Errors: {errors}."


@windows_mcp_tool()
def get_folder_change_summary(directory_path: str, days: int = 7, limit: int = 100) -> str:
    """
    Summarize recently created and modified files in a folder tree.
    Deletions cannot be reconstructed without prior monitoring or filesystem journal access.
    """
    if not os.path.isdir(directory_path):
        return f"Error: Directory '{directory_path}' does not exist."

    cutoff = datetime.datetime.now().timestamp() - (days * 86400)
    created: list[tuple[float, str, int]] = []
    modified: list[tuple[float, str, int]] = []

    for root, _, files in os.walk(directory_path):
        for filename in files:
            path = os.path.join(root, filename)
            try:
                stat = os.stat(path)
                if stat.st_ctime >= cutoff:
                    created.append((stat.st_ctime, path, stat.st_size))
                if stat.st_mtime >= cutoff:
                    modified.append((stat.st_mtime, path, stat.st_size))
            except Exception:
                continue

    created.sort(reverse=True)
    modified.sort(reverse=True)
    lines = [f"Folder change summary for '{directory_path}' over {days} day(s):"]
    lines.append(f"Created files: {len(created)}")
    for timestamp, path, size in created[:limit]:
        date = datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"  {date} | {_format_size(size):>10} | {path}")

    lines.append(f"\nModified files: {len(modified)}")
    for timestamp, path, size in modified[:limit]:
        date = datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"  {date} | {_format_size(size):>10} | {path}")

    return "\n".join(lines)


@windows_mcp_tool()
def disk_cleanup_report(
    directory_path: str,
    days_unused: int = 90,
    min_large_file_mb: float = 100.0,
    min_duplicate_mb: float = 25.0,
    limit: int = 15,
    max_files_scanned: int = 50000,
) -> str:
    """
    Build a read-only cleanup report for a folder tree.
    The report combines drive usage, largest folders, largest files, large media,
    old unused files, likely duplicates, and suggested safe follow-up tools.
    """
    if not os.path.isdir(directory_path):
        return f"Error: Directory '{directory_path}' does not exist."

    root_path = os.path.abspath(directory_path)
    now = datetime.datetime.now().timestamp()
    unused_cutoff = now - (days_unused * 86400)
    large_file_threshold = int(min_large_file_mb * 1024 * 1024)
    duplicate_threshold = int(min_duplicate_mb * 1024 * 1024)
    media_exts = {
        ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm",
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp",
        ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a",
    }

    scanned_files = 0
    skipped_errors = 0
    total_scanned_bytes = 0
    folder_sizes: dict[str, int] = {}
    largest_files: list[tuple[int, str]] = []
    large_media: list[tuple[int, str]] = []
    unused_files: list[tuple[int, float, str]] = []
    duplicate_candidates: dict[int, list[str]] = {}

    try:
        drive_total, drive_used, drive_free = shutil.disk_usage(root_path)
    except Exception:
        drive_total = drive_used = drive_free = 0

    for current_root, _, filenames in os.walk(root_path):
        for filename in filenames:
            if scanned_files >= max_files_scanned:
                break

            file_path = os.path.join(current_root, filename)
            try:
                if os.path.islink(file_path):
                    continue

                stat = os.stat(file_path)
                size = stat.st_size
                scanned_files += 1
                total_scanned_bytes += size

                parent = os.path.abspath(current_root)
                while parent.startswith(root_path):
                    folder_sizes[parent] = folder_sizes.get(parent, 0) + size
                    if parent == root_path:
                        break
                    next_parent = os.path.dirname(parent)
                    if next_parent == parent:
                        break
                    parent = next_parent

                if size >= large_file_threshold:
                    largest_files.append((size, file_path))

                if os.path.splitext(filename)[1].lower() in media_exts and size >= large_file_threshold:
                    large_media.append((size, file_path))

                if stat.st_atime < unused_cutoff and stat.st_mtime < unused_cutoff:
                    unused_files.append((size, stat.st_mtime, file_path))

                if size >= duplicate_threshold:
                    duplicate_candidates.setdefault(size, []).append(file_path)
            except Exception:
                skipped_errors += 1
                continue

        if scanned_files >= max_files_scanned:
            break

    largest_files.sort(reverse=True)
    large_media.sort(reverse=True)
    unused_files.sort(reverse=True)
    largest_folders = sorted(folder_sizes.items(), key=lambda item: item[1], reverse=True)

    duplicate_groups: list[list[str]] = []
    for paths in duplicate_candidates.values():
        if len(paths) < 2:
            continue
        by_hash: dict[str, list[str]] = {}
        for path in paths:
            try:
                by_hash.setdefault(_hash_file(path), []).append(path)
            except Exception:
                skipped_errors += 1
        duplicate_groups.extend(group for group in by_hash.values() if len(group) > 1)
        if len(duplicate_groups) >= limit:
            break

    reclaimable_duplicate_bytes = 0
    for group in duplicate_groups:
        try:
            reclaimable_duplicate_bytes += os.path.getsize(group[0]) * (len(group) - 1)
        except Exception:
            continue

    old_file_bytes = sum(size for size, _, _ in unused_files)

    lines = [
        f"Disk cleanup report for: {root_path}",
        f"Scanned: {scanned_files} files, {_format_size(total_scanned_bytes)} visible data",
    ]
    if scanned_files >= max_files_scanned:
        lines.append(f"Note: scan stopped at max_files_scanned={max_files_scanned}.")
    if skipped_errors:
        lines.append(f"Skipped unreadable items: {skipped_errors}")

    if drive_total:
        used_percent = (drive_used / drive_total) * 100
        lines.extend([
            "",
            "Drive usage:",
            f"  Used: {_format_size(drive_used)} / {_format_size(drive_total)} ({used_percent:.1f}%)",
            f"  Free: {_format_size(drive_free)}",
        ])

    lines.extend(["", "Largest folders:"])
    for folder, size in largest_folders[:limit]:
        lines.append(f"  {_format_size(size):>10}  {folder}")
    if not largest_folders:
        lines.append("  None found.")

    lines.extend(["", f"Largest files over {min_large_file_mb:.1f} MB:"])
    for size, path in largest_files[:limit]:
        lines.append(f"  {_format_size(size):>10}  {path}")
    if not largest_files:
        lines.append("  None found.")

    lines.extend(["", f"Large media over {min_large_file_mb:.1f} MB:"])
    for size, path in large_media[:limit]:
        lines.append(f"  {_format_size(size):>10}  {path}")
    if not large_media:
        lines.append("  None found.")

    lines.extend(["", f"Old unused files over {days_unused} days:"])
    for size, modified, path in unused_files[:limit]:
        modified_date = datetime.datetime.fromtimestamp(modified).strftime("%Y-%m-%d")
        lines.append(f"  {_format_size(size):>10}  modified {modified_date}  {path}")
    if not unused_files:
        lines.append("  None found.")

    lines.extend(["", f"Duplicate groups over {min_duplicate_mb:.1f} MB:"])
    for index, group in enumerate(duplicate_groups[:limit], start=1):
        try:
            group_size = os.path.getsize(group[0])
        except Exception:
            group_size = 0
        lines.append(f"  Group {index}: {len(group)} copies, {_format_size(group_size)} each")
        lines.extend(f"    {path}" for path in group)
    if not duplicate_groups:
        lines.append("  None found.")

    lines.extend([
        "",
        "Cleanup estimate:",
        f"  Duplicate bytes recoverable if one copy per group is kept: {_format_size(reclaimable_duplicate_bytes)}",
        f"  Total bytes in old unused files: {_format_size(old_file_bytes)}",
        "",
        "Suggested safe next actions:",
        "  Use safe_delete_to_recycle_bin for specific files/folders you confirm are disposable.",
        "  Use compress_old_files to archive old files before removing anything.",
        "  Use find_process_locking_file if a file cannot be moved or deleted.",
        "  Use delete_file only when permanent deletion is intentional.",
    ])

    return "\n".join(lines)
