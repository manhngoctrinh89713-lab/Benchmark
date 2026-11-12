# server MCP

当前提供 37 个公开接口。

## 支持的能力

查询目标 Linux 服务器的系统、磁盘、进程、服务及网络连接观测；启动停止重启重载服务、设置开机启动、发送进程信号、重启服务器；查询修改文件权限；读取修改校验服务配置、查询清理日志；读取写入复制移动删除常规文件，查询创建删除空目录；管理环境变量和计划任务、查询任务执行记录；分析目录并创建、查询、校验、恢复和删除备份。

## 对象与操作语义

管理的是目标 Linux 服务器模型。服务启动、重载和重启沿用配置校验、依赖检查、进程与日志联动。配置规则可标记 `restart_required`：该键相对当前生效配置发生变化时，reload 会明确拒绝并要求 restart。服务开机启用与当前运行状态独立；环境变量保存系统及用户范围，新服务进程读取启动时的系统变量快照。

常规文件读写、复制移动删除与服务配置、日志操作分开；配置继续使用专用入口。目录列表包含现有文件形成的目录和显式登记的空目录。文件变更检查校验值、路径、磁盘容量及进程占用。

计划任务支持服务 start、stop、restart、reload，环境推进时间时调用相同服务操作并保存结果。网络查询返回环境最近记录的连接、监听端口和观测时间；没有观测数据时返回空集合。

主机调度入口为 `tools/shared/maintenance/local_maintenance/environment.py`，不向 Agent 注册。该模型不提供任意 SSH 命令、内核、容器编排或完整网络协议栈。

## 接口目录

- `server_analyze_directory`：按Linux绝对路径分析真实场景文件的大小、数量和大文件。
- `server_change_service`：模拟start/stop/restart/reload/enable/disable，联动进程和日志；启动校验配置及依赖。
- `server_copy_file`：复制常规文件到新路径，保留源文件且不覆盖目标。
- `server_create_backup`：将登记备份范围内的服务配置或数据文件写入真实ZIP与清单。
- `server_create_directory`：登记空目录，后续文件可写入该目录。
- `server_delete_backup`：删除本地备份归档及登记，释放模拟磁盘空间。
- `server_delete_file`：删除常规文件，核对当前内容并检查进程占用。
- `server_delete_scheduled_task`：删除计划任务，保留既有执行记录。
- `server_get_disk_usage`：读取模拟挂载点的基础、真实配置/日志/数据文件及备份占用。
- `server_get_environment_variables`：读取目标机器的用户或系统环境变量。
- `server_get_permissions`：读取服务器路径的所有者、用户组和权限模式；递归时包含整棵子树。
- `server_get_process`：读取场景PID详情、服务关联及资源，包含已终止进程。
- `server_get_service`：读取服务启用/运行状态、主PID、依赖及磁盘配置与生效配置的哈希差异。
- `server_get_system_info`：读取模拟Linux系统、资源、磁盘及失败服务概况。
- `server_list_backups`：分页列出当前服务器的本地备份记录。
- `server_list_directory`：列出挂载点下的直接文件和目录，包括已登记的空目录。
- `server_list_network_connections`：查询环境最近记录的网络连接和监听端口，返回观测时间与所属进程。
- `server_list_processes`：搜索当前进程命令并排序；初始进程由提取的Linux MCP ps解析器读入。
- `server_list_scheduled_tasks`：列出目标机器的计划任务和下次执行时间。
- `server_list_services`：按active/inactive/failed和名称搜索本服务器的systemd服务。
- `server_list_task_runs`：查询计划任务的真实模型执行结果和失败信息。
- `server_move_file`：移动常规文件，不覆盖目标；服务配置和日志通过各自入口管理。
- `server_prune_logs`：预览或删除指定服务较早的日志，保留最新keep_last条；其他服务日志保持不变。
- `server_query_logs`：查询真实场景JSONL日志；优先级0最严重，筛选0..max_priority，结果按时间倒序。
- `server_read_file`：读取登记挂载点内的UTF-8场景文件、大小和哈希；最多200000字节。
- `server_read_service_config`：读取登记服务配置的真实UTF-8文本和SHA-256，不读取宿主机/etc。
- `server_reboot`：模拟重启整机：停止本机服务并记录重启事件。
- `server_remove_directory`：删除已登记的空目录。
- `server_restore_backup`：从校验后的ZIP恢复原路径；覆盖需显式指定，配置恢复后仍须重新加载服务。
- `server_save_scheduled_task`：新增或修改计划任务。电脑支持 application.launch；服务器支持 service.start/stop/restart/reload。零间隔为一次性任务。
- `server_set_environment_variable`：设置环境变量，null 删除变量；修改影响后续新建进程。
- `server_set_permissions`：调整服务器路径的所有者、用户组和权限模式（八进制，如 0755）；可递归应用于整棵子树。
- `server_signal_process`：向模拟进程发送TERM/KILL/STOP/CONT；主进程终止会使关联服务失败并写日志。
- `server_validate_service_config`：按场景声明的JSON/INI/ENV语法和必填字段规则校验真实配置；不运行服务二进制。
- `server_verify_backup`：验证ZIP整体及逐文件哈希、机器身份和恢复路径。
- `server_write_file`：在登记挂载点创建或修改文本文件；服务配置沿用专用配置入口。
- `server_write_service_config`：按原文件哈希保存待生效配置；允许先保存错误配置，校验及reload/restart另行调用。
