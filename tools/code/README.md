# code MCP

当前提供 22 个公开接口。

## 支持的能力

列出项目、项目统计及文件，读取和搜索代码；查询符号、符号体、引用和 Python 语义关系；按文本、行、符号或多文件编辑，插入代码和重命名符号；创建、移动、删除及比较代码文件；预览修改、验证语法、分页诊断项目、查询变更和差异。

## 对象与操作语义

项目 ID 指向工作区中的项目目录，文件路径相对于所选项目。文件操作复用现有多文件变更机制，支持内容校验、差异预览和语法校验。移动表现为统一提交中的删除与新增；文本内容保留，目标文件不覆盖。

项目检查包括文件及语言分布、常见配置文件、按路径搜索和分页语法诊断。结构分析沿用 Tree-sitter，Python 引用和重命名沿用 Jedi。语法诊断与项目实际构建、测试结果分别看待；本组不把静态诊断通过记为测试通过，也不运行宿主命令。

## 接口目录

- `apply_workspace_edit`：一次整体修改1..100个文件；每项path、content和可选expected_sha256。content字符串创建/覆盖，null删除。目标不得重复或嵌套；全部检查通过才发布。
- `compare_code_files`：比较项目中两份代码的文本及校验值。
- `create_code_file`：创建真实代码、配置或文本文件，自动创建父目录且不覆盖；可选语法校验。
- `delete_code_file`：按当前校验值删除代码文件，可先预览差异。
- `diagnose_project`：对匹配文件分页进行静态语法诊断，不运行项目代码。
- `find_references`：仅Python：用Jedi静态分析查找光标符号在项目内的引用和定义，排除文本中的字符串与注释。line从1、column按字符从0开始。
- `find_symbol`：在文件或项目内按name_path的子串查找定义，可返回源码；解析失败文件在skipped中报告。
- `get_changes`：比较实际运行代码与初始模板，分页返回新增、修改、删除及哈希，可附unified diff，不依赖Git。
- `get_diagnostics`：返回真实语法诊断。Python编译但不执行代码；其他支持语言使用Tree-sitter。不是类型检查、lint或测试结果。
- `get_project_info`：读取项目文件数量、语言分布和配置文件位置。
- `get_symbols_overview`：用Tree-sitter返回函数、类、方法等定义的name_path和范围；name_path以/分隔，行号1起、字符列号0起。
- `insert_relative_to_symbol`：在完整行定义的before/after插入代码，适配同层缩进，默认检查语法；行内声明使用精确文本编辑。
- `list_code_files`：分页列出项目文件；pattern为区分大小写的相对路径glob，跳过Git、虚拟环境和依赖目录。
- `list_projects`：查看本轮可操作的代码项目、真实根目录、结构分析和语义分析支持的语言。
- `move_code_file`：在项目内移动代码文件，保留文本内容；返回删除与新增的统一预览。
- `read_code`：读取真实UTF-8代码/配置文件，可指定从1开始的闭区间行号，返回原字节sha256。
- `rename_symbol`：仅Python：由Jedi计算项目内符号引用的跨文件重命名，先检查全部输出并检查语法，再作为一次修改发布；不重命名模块/文件。
- `replace_lines`：替换从1起的闭区间行；end_line=start_line-1表示插入，空content可删除。支持差异预览、哈希校验和语法校验。
- `replace_symbol_body`：替换唯一name_path对应的完整定义，包括签名、函数体及所含装饰器/导出包装；body提供完整定义。自动适配嵌套缩进，默认检查语法。
- `replace_text`：依次应用old_text/new_text精确替换；可选expected_count默认1，必须命中该次数。全部检查成功才写入，支持预览与哈希校验。
- `search_code`：按文本精确搜索项目文件，返回路径、行号和命中行；不是语义引用查找。
- `search_project_files`：按相对路径通配符和扩展名查询项目文件。
