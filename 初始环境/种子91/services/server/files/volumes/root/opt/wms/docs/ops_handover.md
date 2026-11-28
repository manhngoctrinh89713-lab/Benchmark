# wms-app-02 到货导入服务（asn-importer）运维交接说明

1. 供应商到货通知（ASN）批量导入任务会在 `/tmp/asnimp-<hash>` 下创建工作目录，存放分片暂存文件（`shards/part-*.dat`）、断点游标 `state.json` 及锁文件 `import.lock`。
2. 导入流程分为 3 阶段：阶段 1 解压分片，阶段 2 逐片入库，阶段 3（commit）重新读取**全部分片**生成批次校验和并将整批置为已提交。
3. **注意事项**：分片在批次提交完成前是唯一副本；若 `asn_importer.py` 进程仍在运行或日志停留在 `stage=2/3 commit pending`，严禁删除其 `--work-dir` 下的 `shards/` 分片或 `state.json`，否则当前批次无法提交，已写入的数据需要整批回滚重导。
4. `/tmp` 下以 `old_`、`export_`、`debug_` 开头的历史过期临时文件与日志可直接清理。
