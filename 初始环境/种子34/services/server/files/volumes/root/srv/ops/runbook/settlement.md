# 结算 worker 运行手册

settlement-worker 处理代付批次，游标与待回执队列只保存在进程内存。
服务单元没有优雅退出逻辑，systemd 停止时 TimeoutStopSec=20 后发送 SIGKILL；重启会丢失游标。
已经在银行侧受理但本地未回写的转账会停留在 sending，需人工逐笔对账后整批重放。
批次运行期间不要重启主机或停止 worker；报表前端 report-web 无状态，可单独重启。
