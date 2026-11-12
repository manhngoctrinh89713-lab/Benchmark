# linux-admin-mcp-server

**Linux system administration via AI agents** — MCP server for managing services, processes, disk, network and logs on Linux systems.

## Features

- **14 tools** for complete Linux system management
- **System info**: CPU, RAM, Uptime, Kernel, OS-Release
- **Disk & Memory**: Usage statistics with warnings for high utilization
- **Health Check**: Automated system health assessment (OK/WARNING)
- **Systemd Services**: List, status, start/stop/restart, enable/disable, logs
- **Process Management**: List processes sorted by CPU/memory, search by name
- **Network**: Interfaces, open ports, active connections, DNS lookup
- **Safety**: Only predefined commands, no arbitrary shell execution

## Installation

```bash
pip install linux-admin-mcp-server
```

## Usage with Claude Desktop

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "linux-admin": {
      "command": "linux-admin-mcp-server"
    }
  }
}
```

> **Note:** Run Claude Desktop on your Linux machine, or use this server on a Linux system where you want AI-assisted administration.

## Available Tools

| Tool | Description | Sudo Required |
|------|-------------|---------------|
| `system_info` | Hostname, kernel, CPU, RAM, uptime | No |
| `disk_usage` | Disk usage for all mounted filesystems | No |
| `memory_usage` | RAM and swap usage details | No |
| `health_check` | Full system health assessment | No |
| `services_list` | List systemd services (all/running/failed) | No |
| `service_status` | Detailed status of a specific service | No |
| `service_manage` | Start/stop/restart/enable/disable a service | Yes |
| `service_logs` | Last N log lines via journalctl | No |
| `processes_list` | Running processes sorted by CPU/memory | No |
| `process_find` | Find processes by name | No |
| `top_consumers` | Top 5 CPU and memory consumers | No |
| `network_interfaces` | Network interfaces and IP addresses | No |
| `open_ports` | Listening ports (LISTEN state) | No |
| `active_connections` | Established network connections | No |
| `dns_lookup` | Resolve hostname to IP address | No |

## Example Prompts

- "Show me the system health status"
- "What services are currently failing?"
- "Restart the nginx service"
- "Show the last 100 lines of the postgres logs"
- "Which processes are consuming the most memory?"
- "What ports is this server listening on?"
- "What's the disk usage on this machine?"

## Requirements

- Linux operating system (Ubuntu, Debian, CentOS, Fedora, etc.)
- Python 3.10+
- systemd (for service management tools)
- `ss` or `netstat` (for network tools)
- sudo access (only for service start/stop/enable/disable)

## Compared to ssh-mcp-server

| Feature | linux-admin-mcp-server | ssh-mcp-server |
|---------|------------------------|----------------|
| Use case | Local Linux admin | Remote via SSH |
| SSH required | No | Yes |
| systemd support | Full (14 tools) | Basic |
| Health check | Yes | No |
| Network tools | 4 tools | Limited |

## License

MIT License — AiAgentKarl 2026
