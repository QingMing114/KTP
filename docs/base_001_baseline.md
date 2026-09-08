# BASE-001 共享开发基线

> 状态：有效  
> 日期：2026-09-08  
> 适用范围：算法工具化目标开始前的共享工程基线

## 1. Git 基线

阶段 0 开始时，本地 `main` 相对 `origin/main` 超前以下三个检查点提交：

- `5953a1e feat(backend): harden canonical runtime workflows`
- `ea15238 feat(frontend): add map-first workspace workflows`
- `8aa829a chore: document and automate the product baseline`

本阶段完成后，应将 `BASE-001` 修复作为独立提交追加在以上提交之后。开始多人并行工作前，必须先把这条连续提交链推送到共享远端，并要求所有工作包从同一个远端提交创建分支。不得从旧的 `origin/main` 派发算法工作。

推送属于共享状态变更，由仓库维护者在本地回归通过并确认提交内容后执行；阶段 0 的自动修复过程不擅自推送。

## 2. 质量门禁

共享 CI 必须执行：

1. 后端受控测试。
2. 前端 ESLint，要求零 warning。
3. 前端测试。
4. 前端生产构建。

2026-09-08 进入阶段 0 时的基线为：后端 182 passed（1 warning）、前端 92 passed、前端生产构建通过。阶段 0 新增 ESLint 为正式阻断门禁。

## 3. APSIM 决策

- `ApsimX/` 保持为锁定提交的 Git submodule，不把上游源码复制进业务代码。
- APSIM 是既有 `apsim.*` 工具的可选外部运行依赖，不是作物分类、地物分割和污染分割三个新工具的开发前置条件。
- 默认离线测试和共享 CI 不初始化或编译 APSIM；对应测试应明确 skip 外部依赖用例，不能伪造运行结果。
- 调用 `apsim.*` 时如果未配置 `APSIM_MODELS_BIN`、模板或验证数据，必须返回明确不可用/失败信息。
- 只有涉及 APSIM 本身的专项验收或发布检查，才按 README 初始化锁定子模块并配置真实运行时。

因此，APSIM 未初始化不阻塞 `STD-001` 和目标一的三个新算法审计。

## 4. 农田障碍物检测决策

稳定能力名预留为 `remote_sensing.farmland_obstacle_detection`，状态为 `unavailable`。在 `STD-001` 冻结统一可用性契约前，不向当前注册表添加临时占位 Tool，避免形成第二套或不可兼容的 Manifest 语义。

恢复为可开发状态至少需要：

- 可审计的算法仓库、版本和许可证。
- 可复现的推理入口、依赖锁和硬件要求。
- 合法可用的模型权重及其版本、来源和校验和。
- 数据集地址、许可证、样本格式和训练/验证划分。
- “障碍物”的产品定义、类别表、忽略类和最低目标尺寸。
- 输入传感器、波段、空间分辨率、CRS 和预处理规则。
- 输出几何/掩膜格式、置信度、评价指标和验收阈值。
- 至少一个可合法分发的 smoke test 样例。

上述信息不全时，不得使用 mock 或其他检测模型冒充该能力。

## 5. 阶段 0 出口条件

- ESLint 配置存在且本地、CI 均执行 `npm run lint`。
- 前后端既有测试和构建不回退。
- APSIM 的非阻塞边界和专项启用条件已有记录。
- 障碍物检测明确为不可用，并记录恢复所需资料。
- 开发计划与 Memory 更新为 `BASE-001` 完成、`STD-001` 下一步。
- 共享远端发布策略已确定；实际推送由维护者确认执行。

## 6. 验证记录

2026-09-08 在 Windows、Conda `ktp-dev`、Node.js 当前锁定依赖环境完成：

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 后端受控基线 | `python -m pytest backend/tests backend/v2/tests tests/test_product_protocol_api.py -q` | 182 passed，1 个既有 Starlette/httpx deprecation warning |
| 前端静态检查 | `npm run lint` | 通过，0 warning |
| 前端测试 | `npm test -- --reporter=dot` | 13 files、92 tests 全部通过 |
| 前端构建 | `npm run build` | 通过 |

Vitest/Vite 输出包含依赖侧 `esbuild` 选项弃用提示，不影响本次门禁；后续依赖升级工作应单独切包处理。
