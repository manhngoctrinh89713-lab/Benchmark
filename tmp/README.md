# tmp 保留内容

2026-11-11 清理后，这里只保留历史评审文档直接引用的结果文件；其余一次性脚本、下载、备份、测试日志和临时环境已删除。运行入口在 `src/harness/runner.py`，批量调度在 `tools/run_three_models.py`，不再依赖本目录。

保留文件：

- `full-suite-after-judge-fixes.log`、`full-suite-after-seed1-fix.log`、`full-suite-final.log`：全量测试日志（`评测函数/reviews` 引用）
- `seed25-full-tests.log`、`seed25-independence-tests.log`、`seed25-spreadsheet-tests.log`：种子25专项测试日志（评审文档引用）
- `seed37_rescore.json`：种子37复评分输出（评审文档引用）

需要新的临时脚本时，请放在本目录并在完成后删除；不要把运行入口或长期依赖放在这里。
