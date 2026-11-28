# fin-report

财务中台多分支机构月结报表导出服务（Python 3.12）。

## 目录结构
- `config/`: 环境与导出流水线配置（dev / staging / export）
- `reporting/api/`: HTTP 导出接口与健康检查
- `reporting/core/`: 导出调度与扩展加载
- `reporting/models/`: 账务行与报表元数据模型
- `reporting/formatters/`: CSV / JSON 格式化模块
- `reporting/validators/`: 字段与金额校验
- `reporting/guards/`: 分公司数据范围过滤模块（v2 已上线开发与测试环境）
- `scripts/`: 批处理入口
- `tests/`: 单元测试
