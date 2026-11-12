# pc MCP

当前提供 38 个公开接口。

## 支持的能力

查询目标 Windows 电脑的系统、磁盘、应用、进程、缓存和个人文件；安装更新卸载应用、启动应用、挂起恢复终止进程；管理开机启动项、应用声明的设置、用户和系统环境变量；创建修改查询删除计划任务并查询执行记录；分析和清理缓存；读写、复制、移动、删除个人文件，管理回收站；创建、查询、校验、恢复和删除备份。

## 对象与操作语义

管理的是目标电脑模型。个人文件保存真实字节，应用、进程、启动项、设置和环境变量保存资源状态。应用设置只能修改环境声明的字段及类型。环境变量变化影响新进程，新建进程保留启动时快照。

计划任务支持定时启动已安装应用，可设一次性或固定秒数周期；最短周期六十秒。环境控制器推进时间时调用现有应用启动操作，保存每次成功或失败记录。读取任务、进程或文件不会触发任务。

回收站与直接删除分开。回收文件保留原路径、字节与校验值，并计入原磁盘占用。恢复支持另选个人目录，不覆盖现有文件；永久清除释放空间。已有 ZIP 备份功能继续保留。

主机调度入口为 `tools/shared/maintenance/local_maintenance/environment.py`，不向 Agent 注册。该组不执行宿主 Windows 程序，也不提供任意注册表或驱动操作。

## 接口目录

- `pc_analyze_directory`：分析登记磁盘内目录的真实场景文件大小、数量和大文件。
- `pc_change_process`：挂起、恢复或终止指定模拟进程；保护系统进程，不使用宿主机PID。
- `pc_clean_cache`：预览或清理登记缓存中的过期文件，跳过模拟进程正在使用的文件。
- `pc_copy_personal_file`：复制个人文件到新位置，核对源文件且不覆盖目标。
- `pc_create_backup`：将登记个人文件备份为真实ZIP及校验清单；支持幂等重试。
- `pc_delete_backup`：删除一个本地ZIP备份和记录，释放模拟备份磁盘空间。
- `pc_delete_personal_file`：按预期哈希删除一个个人文件；模拟进程使用中的文件不能删除。
- `pc_delete_recycled_file`：永久删除回收站文件并释放空间。
- `pc_delete_scheduled_task`：删除计划任务，保留既有执行记录。
- `pc_delete_startup_item`：删除一个非系统保护的开机启动项。
- `pc_get_application_settings`：读取应用设置及环境提供的可修改设置定义。
- `pc_get_disk_usage`：按模拟卷统计系统基础占用、应用、真实场景文件和ZIP备份占用。
- `pc_get_environment_variables`：读取目标机器的用户或系统环境变量。
- `pc_get_process`：读取指定场景PID的状态、应用关联、资源和打开文件；含已终止记录。
- `pc_get_system_info`：读取场景Windows电脑的系统信息、内存、进程和磁盘概况。
- `pc_launch_application`：为已安装应用创建本地模拟进程；不执行其命令或程序。
- `pc_list_applications`：搜索应用目录；默认只看已安装应用，可查询可安装版本和占用。
- `pc_list_backups`：分页列出当前电脑的备份记录及归档哈希。
- `pc_list_cache_locations`：列出可清理的登记缓存位置、实际文件数量和占用。
- `pc_list_personal_files`：在登记个人文件根内分页列出真实文件、大小和哈希。
- `pc_list_processes`：按名称搜索当前进程并按内存、CPU或PID排序；使用提取的上游进程过滤逻辑。
- `pc_list_recycle_bin`：列出可恢复的个人文件。
- `pc_list_scheduled_tasks`：列出目标机器的计划任务和下次执行时间。
- `pc_list_startup_items`：列出模拟Windows开机启动项、来源、应用和启用状态。
- `pc_list_task_runs`：查询计划任务的真实模型执行结果和失败信息。
- `pc_manage_application`：在本地状态中安装、更新或卸载登记应用；运行中应用须先退出，磁盘占用同步变化。
- `pc_move_personal_file`：移动或重命名个人文件，核对源文件且不覆盖目标。
- `pc_read_personal_file`：读取登记个人文件中的UTF-8文本及原始字节SHA-256。
- `pc_recycle_file`：将个人文件移入回收站，保留内容和原始路径。
- `pc_restore_backup`：从已校验ZIP恢复原个人文件；默认拒绝覆盖，可幂等重试。
- `pc_restore_recycled_file`：从回收站恢复文件，已有目标不覆盖。
- `pc_save_scheduled_task`：新增或修改计划任务。电脑支持 application.launch；服务器支持 service.start/stop/restart/reload。零间隔为一次性任务。
- `pc_save_startup_item`：新增或修改应用开机启动项。
- `pc_set_environment_variable`：设置环境变量，null 删除变量；修改影响后续新建进程。
- `pc_set_startup_item`：启用或禁用登记启动项；不修改真实注册表或启动文件夹。
- `pc_update_application_settings`：修改应用声明支持的设置，按类型、选项和数值范围校验。
- `pc_verify_backup`：校验ZIP整体哈希、清单、逐文件内容和恢复路径范围。
- `pc_write_personal_file`：创建或更新个人文本文件；更新必须提供原字节哈希以防覆盖其他修改。
