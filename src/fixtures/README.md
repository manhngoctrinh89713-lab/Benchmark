# 初始环境构建脚本

这些脚本生成 `初始环境/` 下的文件和服务状态，属于维护工具，不参与运行调度。

工具 API 的状态模型变化后，构建脚本只负责生成种子内容；生成的 `services/*/state.json` 还需要通过当前 Store 迁移一次，才能补齐新的集合、版本字段和默认值。生成后执行：

```powershell
.venv/Scripts/python.exe -B tools/normalize_initial_environments.py
```

该脚本会逐种子载入对应 Store，执行原有迁移、校验并回写状态；重复执行是幂等的。迁移前的状态快照保存在 `.archive/initial-state-pre-20261108/`。

种子36、43、45、40 的构建脚本已直接写入新的 `description`/`policies`、逐员工 SKU、`restart_required` 和 `applied_config`；其余脚本仍可继续使用，但生成后必须运行上面的迁移脚本。

种子25使用独立构建入口 `src/fixtures/种子25/build.py`，`build_seeds_22_25.py`也会调用它。XLSX模板由同目录 `build_workbook.mjs` 使用artifact-tool生成；重建模板需将该目录node_modules连接到Codex运行时依赖。日常重建种子只复制模板，不需要Node。
