#!/usr/bin/env bash
set -euo pipefail
# 发布步骤（执行顺序）：
# 1. 在 orders-db 上执行 db/migrations/0042_drop_legacy_status.sql 并将 '0042' 写入 schema_migrations
# 2. 更新 /etc/order-api/app.env 中 APP_VERSION=v2.4.2 并重启 order-api.service
echo "[1/2] Applying db/migrations/0042_drop_legacy_status.sql to orders-db ..."
echo "[2/2] Rolling out order-api.service to v2.4.2 ..."
