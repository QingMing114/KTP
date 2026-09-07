# 测试分层与可信基线

以下命令均从 `ktp/` 仓库根目录执行。Windows 本地后端使用项目约定的 Conda 环境：

```powershell
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONPATH = "backend"
conda run --no-capture-output -n ktp-dev python -m pytest backend/tests backend/v2/tests tests/test_product_protocol_api.py -q
```

该命令是当前受控后端基线，包含 unit、canonical contract、Runtime 和空间集成测试。测试文件不得通过 `importorskip` 跳过当前 canonical 实现；可选外部服务才允许显式 marker/skip，并必须在输出中说明原因。

## 定向层

```powershell
# canonical contract、持久 Store、鉴权和错误信封
conda run --no-capture-output -n ktp-dev python -m pytest backend/tests tests/test_product_protocol_api.py -q

# bounded runtime、Policy、重规划、取消、Memory 和 /v2 兼容
conda run --no-capture-output -n ktp-dev python -m pytest backend/v2/tests -q

# 地图 LAI：空间校验、STAC、worker、SSE、Artifact
conda run --no-capture-output -n ktp-dev python -m pytest backend/tests/test_spatial_contracts.py backend/tests/test_stac_provider.py backend/tests/test_lai_reporting.py -q
```

## 前端与构建

```powershell
Set-Location frontend
npm ci
npm test -- --reporter=dot
npm run build
```

前端使用锁定的 `jsdom 26.1.0`，避免 jsdom 29 在当前 CommonJS worker 链中造成测试文件未启动但局部用例显示通过。Vitest 输出必须同时满足 `Test Files` 全部通过且没有 `Unhandled Errors`。

## 可选外部/E2E

根目录 `tests/` 中除 `test_product_protocol_api.py` 之外还包含模型、APSIM、外部服务和脚本级测试。这些测试依赖模型权重、服务进程、许可证或真实数据，不计入默认离线基线；发布候选版本应在依赖齐全的专用环境单独执行并归档结果。

## 质量门槛

- 协议或状态机变更必须同时提交失败回归。
- canonical、Runtime、空间集成、前端测试和生产构建是合并阻断项。
- 不把 skipped、未启动 worker 或历史提交的数字记为当前 passed。
- 基线记录必须包含日期、提交/工作区、环境和完整命令。
