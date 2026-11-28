#!/usr/bin/env bash
set -euo pipefail
# 生产一键回滚脚本：仅回滚应用容器镜像版本，不执行任何反向数据库迁移
echo "[ROLLBACK] kubectl rollout undo deployment/order-api"
