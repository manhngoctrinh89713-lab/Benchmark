# git MCP

当前提供 33 个公开接口。

## 支持的能力

查询仓库、状态、差异、提交、分支、标签、逐行归属、文件历史及引用记录；读取和修改工作区文件；创建、切换、重命名和删除分支，创建删除标签；暂存、撤销暂存、提交、重置暂存区、按提交恢复选定文件；管理 stash；合并、变基、压缩提交、挑选和撤销提交，处理冲突并继续或中止；管理远程地址，抓取和推送到登记远程。

## 对象与操作语义

使用真实 Git 仓库及既有受限命令执行器，操作结果来自 Git。标签区分轻量和附注标签；分支删除默认要求已合并，force 参数用于显式删除。文件恢复可以单独覆盖工作区或同时覆盖暂存区，撤销暂存保留工作区内容。

stash 支持 list、push、show、apply、pop、drop，并返回冲突信息。cherry-pick 和 revert 支持开始、继续、跳过和中止；冲突后通过现有文件修改与暂存入口解决。操作状态统一识别 merge、rebase、cherry-pick 和 revert。

远程抓取和推送继续限制在登记的本地远程模型。现有接口与新增接口均不调用测试集。子模块、LFS、签名基础设施和远程托管权限由各自系统管理。

## 接口目录

- `git_add`：暂存指定路径；传["."]暂存全部。路径相对仓库，按字面匹配。
- `git_blame`：读取文件选定行在指定提交中的逐行归属。
- `git_branches`：列出本地分支、SHA和当前分支。
- `git_checkout`：切换已有本地分支，要求工作区和暂存区干净。
- `git_cherry_pick`：挑选一个提交，支持冲突后的 continue/skip/abort。
- `git_commit`：提交暂存区，返回真实提交SHA；无暂存变化时报错，不自动暂存。
- `git_create_branch`：从已有提交创建本地分支，不切换。
- `git_create_tag`：在指定提交创建轻量标签，提供说明时创建附注标签。
- `git_delete_branch`：删除本地分支；默认要求分支已合并。
- `git_delete_tag`：删除本地标签。
- `git_diff`：查看真实Git差异，mode为unstaged/staged/refs；refs需base和head。禁用external diff和textconv。
- `git_fetch`：从本地模拟远程更新远程跟踪引用；prune 删除远程已不存在的引用。
- `git_file_history`：查询文件历史，跟踪单文件重命名。
- `git_log`：读取提交历史，limit为1..100。
- `git_merge`：合并提交或分支到当前本地分支。operation=start/continue/abort；start需source，ff_mode=ff/no-ff/ff-only，message可选。开始前须无进行中操作且工作区干净。冲突返回conflicts并保留现场，编辑文件、git_add后continue，也可abort。不会自动fetch或push。
- `git_operation_status`：查询当前merge/rebase操作、未解决冲突文件、当前分支、HEAD及工作区状态；operation=null表示没有进行中的操作。冲突路径相对于所选仓库。
- `git_push`：把本地分支推送到本地模拟远程；force=false 拒绝非快进，force=true 覆盖。
- `git_rebase`：变基当前本地分支。operation=start/continue/skip/abort；start需upstream，可用onto指定新基线，rebase_merges=true重建合并拓扑，默认线性重放。开始前须工作区干净且无进行中操作。冲突返回conflicts，编辑文件并git_add后continue；skip会丢弃当前重放提交，abort恢复变基前状态。不会自动fetch或push。
- `git_reflog`：查询本地引用移动记录，供定位历史提交和恢复操作使用。
- `git_remote`：列出、添加或移除本地模拟远程；只保存 URL 和引用，不联网。
- `git_rename_branch`：重命名本地分支，目标名称已存在时失败。
- `git_reset`：仅取消全部暂存，保留工作文件和提交；不提供hard reset。
- `git_restore_files`：用指定提交恢复选定文件的工作区内容，可同时恢复暂存区。
- `git_revert`：以新提交撤销历史提交，支持 continue/skip/abort。
- `git_show`：查看指定提交内容及差异。
- `git_squash`：把当前本地分支在base之后的全部提交压缩为一个提交，新提交以base为父提交，完整保留当前最终文件树（含删除、二进制及权限）。base须为HEAD的严格祖先，开始前须工作区干净且无merge/rebase进行中。改写本地历史，不自动获取、保留远程新增修改或推送。
- `git_stash`：保存、列出、查看、应用、弹出或删除 stash。
- `git_status`：读取真实Git工作区和暂存区状态。
- `git_tags`：列出轻量和附注标签及其提交标识。
- `git_unstage`：撤销指定路径的暂存，保留工作区修改。
- `list_repositories`：查询可操作的模拟仓库和对应运行路径。
- `read_repository_file`：读取UTF-8代码文件，省略revision读取工作区，否则读取指定提交版本；不允许访问.git。
- `write_repository_file`：写入UTF-8工作文件，不自动暂存。默认不覆盖，最大1 MiB，不允许修改.git。
