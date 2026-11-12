# Tool Catalog

Windows Management MCP Server exposes 96 tools grouped by domain. Some tools are read-only, some mutate local system state, and some are intentionally powerful.

## Task Manager

- `get_cpu_usage`: Overall and per-core CPU load.
- `get_gpu_usage`: GPU 3D engine utilization through Windows counters.
- `get_memory_usage`: RAM totals, used, and available memory.
- `get_disk_usage`: Drive usage across mounted disks.
- `get_top_processes`: Top processes by CPU or memory.

## Process and Window Management

- `get_process_details`: PID details, command line, parent, resources, open files, sockets, and signature.
- `get_process_tree`: Parent-child process relationships.
- `find_process_locking_file`: Visible process handles for a file.
- `kill_process`: Kill by PID or exact process name.
- `suspend_process`: Suspend a process by PID.
- `resume_process`: Resume a suspended process by PID.
- `search_process_by_name`: Search running processes by name substring.
- `list_open_windows`: Visible windows, titles, process names, PIDs, and bounds.
- `focus_window`: Bring a matching visible window forward.
- `close_window`: Ask a matching visible window to close gracefully.

## Storage and Cleanup

- `disk_cleanup_report`: Combined read-only cleanup report.
- `analyze_directory_space`: Largest files and folders in a directory.
- `find_unused_files`: Old untouched files in a folder tree.
- `find_media_files`: Large video, image, and audio files.
- `find_large_duplicates`: SHA-256-confirmed duplicate large files.
- `get_folder_change_summary`: Recently created and modified files.
- `compress_old_files`: Archive old files, optionally deleting originals.
- `safe_delete_to_recycle_bin`: Send one file/folder to Recycle Bin.
- `safe_delete_many_to_recycle_bin`: Send newline-separated paths to Recycle Bin.
- `safe_delete_by_pattern`: Preview or recycle glob matches.
- `delete_file`: Permanently delete one file.
- `delete_files_by_extension`: Permanently delete matching files in one folder.
- `clear_temp_files`: Clear `%TEMP%`, `%TMP%`, and `C:\Windows\Temp`.
- `empty_recycle_bin`: Empty the Windows Recycle Bin.

## Disk Health

- `get_smart_disk_health`: Physical disk and SMART status where available.
- `get_volume_health`: Volume/filesystem health and free space.
- `get_disk_io_counters`: Per-disk read/write counters since boot.

## Hardware, GPU, and Drivers

- `get_gpu_details`: GPU model, driver, VRAM, and resolution.
- `get_gpu_processes`: Processes appearing in GPU utilization counters.
- `get_display_configuration`: Video controller and monitor details.
- `get_gpu_performance_summary`: GPU engine and adapter memory counters.
- `get_nvidia_smi_summary`: NVIDIA telemetry through `nvidia-smi` when available.
- `get_gpu_vendor_report`: Vendor and Windows GPU summary.
- `list_installed_drivers`: Installed drivers, optionally by device class.
- `list_problem_devices`: PnP devices that are not healthy.
- `get_driver_update_candidates`: Driver updates available through Windows Update.
- `get_driver_inventory_report`: Driver inventory with dates, versions, INF names.

## Security, Updates, and Restore Points

- `get_security_status`: Defender, firewall, BitLocker, Secure Boot, and UAC.
- `scan_with_defender`: Start quick, full, or custom Defender scan.
- `get_windows_update_status`: Pending updates, reboot state, update history.
- `list_installed_updates`: Installed hotfixes and KB updates.
- `install_windows_updates`: Preview or install software updates.
- `install_driver_updates`: Preview or install driver updates.
- `list_restore_points`: Recent system restore points.
- `get_system_protection_status`: Restore point and shadow storage status.
- `create_restore_point`: Create a system restore point.

## Services, Startup, and Scheduled Tasks

- `list_services`: Windows services by status.
- `manage_service`: Start, stop, pause, or continue a service.
- `list_startup_apps`: Registry Run-key startup entries.
- `get_startup_impact`: Registry, Startup folder, and scheduled startup/logon tasks.
- `list_scheduled_tasks`: Scheduled tasks with state and run history.
- `enable_disable_startup_item`: Toggle registry, scheduled task, or Startup folder startup entries.

## Event Logs and Crash Diagnostics

- `get_event_logs`: Event Viewer query by log, level, source, and time window.
- `diagnose_recent_crashes`: Recent crash, critical, and Windows Error Reporting clues.

## Network and Firewall

- `manage_network`: Interfaces, connections, ping, and Wi-Fi networks.
- `get_network_usage_by_process`: Active sockets grouped by process.
- `get_listening_ports`: Listening ports and owning processes.
- `get_listening_ports_with_firewall`: Listening ports with matching inbound firewall rule data.
- `get_port_firewall_rules`: Firewall rules that reference a local port.
- `test_network_latency`: Ping latency checks.
- `list_firewall_rules`: Windows Defender Firewall rules.

## Registry and PowerShell

- `manage_registry`: Read, write, or delete registry values.
- `execute_powershell`: Run PowerShell, optionally elevated.

## Power and Hardware Health

- `get_system_info`: OS, machine, boot time, uptime.
- `get_hardware_info`: CPU, RAM, and disk summary.
- `get_battery_health`: Battery capacity and charge data where available.
- `get_thermal_status`: Thermal zones and CPU clock/load clues.
- `get_power_plan`: Active and available power plans.
- `set_power_plan`: Switch Windows power plan.

## Software Maintenance

- `list_installed_software`: Installed software from uninstall registry keys.
- `find_uninstall_entries`: Search uninstall entries and commands.
- `uninstall_software`: Preview or launch an uninstaller.

## Developer Environment

- `list_env_vars`: Process, user, or machine environment variables.
- `set_env_var`: Set user or machine environment variable.
- `list_python_installs`: Python executables and launcher registrations.
- `list_node_installs`: Node.js, npm, and npx executables.
- `check_dev_ports`: Common dev ports and owning processes.

## Shell, Clipboard, and Screenshots

- `open_path_in_explorer`: Open folder or select file in Explorer.
- `take_screenshot`: Capture primary or virtual desktop screenshot.
- `get_clipboard_text`: Read text from clipboard.
- `set_clipboard_text`: Set clipboard text.

## Peripherals

- `list_printers`: Installed printers and status.
- `set_default_printer`: Set default printer.
- `list_print_jobs`: Print jobs, optionally for one printer.
- `clear_print_queue`: Preview or clear a printer queue.
- `list_audio_devices`: Audio endpoint devices.
- `list_bluetooth_devices`: Bluetooth devices.

## Virtualization

- `get_wsl_status`: WSL status.
- `list_wsl_distros`: WSL distributions.
- `list_hyperv_vms`: Hyper-V VMs where available.
- `get_windows_optional_features_status`: WSL, Hyper-V, containers, and related feature status.
