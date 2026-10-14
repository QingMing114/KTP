# 按作物识别自动运行 APSIM 示例

2026-10-13。地图工作台的 APSIM 任务默认选择“真实示例模拟”，仍可切换到需要核验资料的地块情景估产。

`data_mode=apsim_example` 依次执行影像准备、农作物识别和 APSIM 示例模拟，不自动加入 LAI 反演。识别类别 0 使用 Maize.apsimx，2 使用 Soybean.apsimx，3/4 使用 Wheat.apsimx。类别 1/5、识别失败、最高分不足 0.60 或前两类分差不足 0.15 时暂停。示例选择来自识别任务结果，不由助手猜测，也不使用手动品种或地块数据替换示例参数。

三个示例均配套使用包内 AU_Dalby.met；保留示例土壤、品种及播种、施肥和收获规则。模拟窗口为 1990-01-01 至 1991-12-31，以覆盖跨年种植季。日报输出 LAI、生物量、籽粒干重和物候阶段；展示期间最高籽粒干重换算的 t/ha，不将其乘以当前 AOI 面积，不声称进行了遥感 LAI 约束。报告展示示例及气象文件名和 SHA-256，并明确不代表当前农田实际产量。

服务端配置：

```
APSIM_EXAMPLE_ROOT=/home/D/zhanghuaxiang_D/apps/ktp/apsim-runtime
APSIM_EXAMPLE_MODELS_BIN=/home/D/zhanghuaxiang_D/apps/ktp/apsim-runtime/bin/Release/net8.0/linux-x64/publish/Models
```

运行包是自包含 Linux 构建。每次任务独立保存准备后的模型、日报、数据库及日志，临时文件使用该任务私有目录。重试先移除旧输出；失败时不读取旧产物或回退为预设曲线。

助手通过 `apsim_mode=example` 创建同一真实工作流；该模式随工作台版本同步并参与草案过期检查。配置与解释请求不会自动启动。原有 `data_mode=demo` 仍是明确请求的预设曲线演示，`data_mode=live` 的 APSIM 地块估产仍执行原有输入核验及同日 LAI 约束。
