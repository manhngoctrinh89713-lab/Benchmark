# database MCP

当前提供 21 个公开接口。

## 支持的能力

查询、创建、重命名和删除 SQLite 数据库；查询数据库信息、表、视图、列、索引、外键关系、结构及表统计；执行参数化查询、查询计划、数据修改、建表和结构变更，以及多语句事务；导入 CSV、导出 CSV 或 JSON、备份与恢复数据库、检查数据库和外键完整性。

## 对象与操作语义

使用真实 SQLite 文件和查询引擎。数据库 ID 与显示名称分开，名称修改不改变 ID。创建空数据库、删除指定数据库以及从工作区备份恢复均有独立入口；删除和恢复记录原文件快照，修改现有数据库前可用 SHA-256 核对。

结构功能按 SQLite 表、视图、索引、外键、触发器和事务提供；复杂结构修改沿用 SQL 入口。表统计返回行数、空值数和不同值数量。SQL 标识符引用与查询参数分别处理，事务内任一语句失败时不提交。

CSV 导入最多 10000 行，查询导出支持 CSV 与 JSON。备份通过 SQLite backup 创建，恢复要求独立且完整的 SQLite 文件。数据库集群、跨库分布式事务、账号角色平台和远程连接管理不属于该模型。

## 接口目录

- `backup_database`：使用SQLite Backup API生成运行files内的新数据库备份，不覆盖；备份可由sqlite3直接打开。
- `check_integrity`：执行数据库完整性及外键检查，返回ok、integrity和foreign_key_violations。
- `create_database`：创建空 SQLite 数据库并登记显示名称。
- `delete_database`：删除指定数据库并记录删除前快照，按当前文件校验值核对目标。
- `describe_table`：读取表或视图的列、生成列、外键、索引及建表SQL。
- `execute_schema`：执行单条结构修改SQL，如建表、索引、视图、触发器、ALTER或DROP；不允许ATTACH、VACUUM INTO或用户PRAGMA。
- `execute_transaction`：以一个真实SQLite事务执行1..100条SQL。每项含sql和可选parameters，允许读写及DDL；任一失败整体不落盘。不可自行BEGIN/COMMIT或跨库ATTACH。
- `explain_query`：使用EXPLAIN QUERY PLAN读取只读查询的执行计划，不执行该查询的数据扫描。
- `export_query`：将只读查询完整导出为运行files内新CSV或JSON，不覆盖。format为csv/json，最多10000行、25 MiB，超限报错而非截断。CSV使用UTF-8 BOM，NULL为空字段。
- `get_database_info`：查询SQLite版本、文件大小、页数、页大小及数据库SHA-256。
- `get_table_statistics`：读取表行数、每列空值数和不同值数量。
- `import_csv`：将运行files内UTF-8 CSV导入已有表，首行是唯一非空列名，最多10000数据行。所有行同一事务；默认空字段仍为空字符串，可指定null_value映射NULL，SQLite按表亲和性转换类型。
- `list_databases`：查询可操作的本地数据库ID和实际SQLite文件路径。
- `list_indexes`：查询数据库索引、列顺序和唯一性。
- `list_relationships`：列出表之间的外键关系及更新、删除行为。
- `list_tables`：列出用户表及可选视图，返回名称、类型与建表SQL。
- `read_query`：执行单条只读SQL，支持SELECT、WITH、JOIN、聚合、窗口函数。参数支持?列表或命名字典。返回columns与rows数组，保留重复列名；limit为1..1000，offset为0..10000。
- `rename_database`：修改数据库显示名称，数据库 ID 和 SQL 内容保持稳定。
- `restore_database`：用工作区内的 SQLite 备份替换已登记数据库，核对当前校验值及备份完整性。
- `search_schema`：按名称或SQL定义子串搜索表、列定义、视图、索引和触发器。offset分页，limit为1..100。
- `write_query`：执行单条DML，支持INSERT/UPDATE/DELETE/REPLACE及WITH。事务成功后保存真实数据库和修改记录。外键/约束失败则不修改运行库。
