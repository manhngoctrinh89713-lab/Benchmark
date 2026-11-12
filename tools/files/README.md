# files MCP

当前提供 28 个公开接口。

## 支持的能力

查询允许目录、文件元数据和目录树，按名称及内容搜索；读取文本、常见文档、多文件及分段二进制；创建目录，写入、追加和编辑文本，写入二进制，比较文件；复制、移动、删除文件或目录；创建、查看和解压 ZIP；将文件或目录移入回收站、查询、恢复和永久清除回收项。

## 对象与操作语义

工作区保存真实文件，操作通过统一变更计划提交。文件元数据提供 SHA-256；覆盖、追加和编辑可核对旧内容。读取二进制按段返回 Base64，写入支持同一格式。文本比较同时返回字节相等性和可选统一差异。

ZIP 打包保留工作区相对路径；解包在提交前检查成员路径、重复目标、文件目录冲突和总大小。单文件上限 25 MiB，单次归档输入或解包上限 100 MiB、最多 10000 项。普通删除直接删除；回收操作把原始路径及内容保存在服务回收区，恢复默认不覆盖。

本组提供工作区文件操作和文档提取。云盘分享、账号授权和协作编辑需要独立的云盘资源模型，不通过修改旁置配置文件充当这些功能。

## 接口目录

- `append_file`：在现有 UTF-8 文件末尾追加文本，并核对修改前的校验值。
- `compare_files`：比较两份文件的字节内容，可返回 UTF-8 文本差异。
- `copy_file`：复制文件或整个目录，保留文件原始字节；目标必须不存在，自动创建父目录。单文件25 MiB、总内容100 MiB、目录10000项以内。
- `create_archive`：将选定文件或目录打包为 ZIP，归档内保留工作区相对路径。
- `create_directory`：创建目录及父目录，已存在目录返回created=false；不能对files根目录执行修改。
- `delete_file`：删除文件或空目录；非空目录须recursive=true。操作限files内部；不存在的路径按空操作处理。
- `delete_trash`：永久删除一个回收站项目。
- `directory_tree`：读取目录树，max_depth为1..20，默认4层；深度边界以depth_limited标记。可排除模式匹配的条目及其子树。最多遍历10000项。
- `edit_file`：顺序应用oldText/newText精确替换；每次oldText必须恰好出现一次，不做模糊匹配。UTF-8文本，比较时规范化CRLF，写回保留原首个换行样式。dry_run只返回diff不修改文件或事件；可传expected_sha256。
- `extract_archive`：将 ZIP 解压到指定目录；预先检查全部目标、重复项和大小后统一提交。
- `get_file_info`：读取文件或目录元数据；文件返回原字节SHA-256。文件最大25 MiB。
- `list_allowed_directories`：返回本次运行唯一允许操作的files根目录及相对路径基准。
- `list_archive`：列出 ZIP 归档中的文件、目录和解压大小。
- `list_directory`：列出直接子项，目录优先、名称排序。path相对files根目录，支持offset分页，limit为1..100。返回名称、类型、大小、时间及文件SHA-256。
- `list_trash`：列出可恢复的回收站项目。
- `move_file`：移动或重命名文件/目录，目标必须不存在，自动创建目标父目录。拒绝源目标嵌套、链接及files根目录。
- `read_binary_file`：分段读取文件二进制内容，以 Base64 返回，并提供完整文件校验值。
- `read_document`：读取一个本地文件为可读文本：文本类原样解码，PDF、DOCX、PPTX、XLSX/XLS、HTML、EPUB、IPYNB自动转Markdown，图片文件返回尺寸等元数据。按行分页，offset从0开始，limit默认读到200000字符上限；返回next_offset用于续读，total_lines/total_characters给出全文规模，warnings说明编码回退、空文本、嵌入图片或行截断。不做OCR，文件最大25 MiB。
- `read_multiple_files`：批量读取1..20个文件，文本、PDF、DOCX、PPTX、XLSX/XLS、HTML与图片均可，单文件错误不影响其余。返回items，失败项含error；各文件内容合计最多200000字符。
- `restore_trash`：恢复回收站项目到原路径或新路径，已有文件不覆盖。
- `search_content`：递归搜索UTF-8文本正文的字面子串，返回路径、行号和匹配行。二进制或不能读取的文件在skipped中报告；Office/PDF请先转换为Markdown再搜索。匹配行最多返回2000字符。
- `search_files`：递归按文件名或相对搜索起点的路径匹配glob；忽略大小写，支持*、?和字符组。*可跨目录分隔符，无特殊**语义。排除命中的目录不再遍历。
- `trash_file`：将文件或目录移入服务回收站，保存原始路径以便恢复。
- `write_binary_file`：将 Base64 内容写入文件，支持按已有文件校验值覆盖。
- `write_file`：以UTF-8创建或写入文本，自动创建父目录。默认不覆盖；覆盖须overwrite=true，可用expected_sha256防止覆盖读取后已变化的文件。

## XLSX工作簿

新增 get_workbook_info、read_spreadsheet、write_spreadsheet。读取返回原值、公式及按当前依赖计算的结果；写入逐格批量更新，核对工作簿SHA-256并保留其他单元格与格式。读取结果不依赖文件内公式缓存，保存标记Excel打开后重新计算。

支持单元格/区域的同表及跨表引用、四则运算、SUM/MIN/MAX、ROUND和精确匹配VLOOKUP。最多100000格工作簿，单次读写2000格，计算深度64、依赖步数20000。不支持的函数、循环引用、错误值明确报告，不执行宏、不访问外部工作簿或网络，不提供完整Excel函数引擎。写入可保存未支持的公式，但读取计算会明确报错。

- `get_workbook_info`：工作表名称、可见性、行列范围和公式数量。
- `read_spreadsheet`：指定工作表和A1区域，读取原值、公式和当前计算结果。
- `write_spreadsheet`：指定工作表，按cell/value批量写入，必须提供expected_sha256。
