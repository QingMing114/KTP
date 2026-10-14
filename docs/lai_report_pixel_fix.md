# LAI 报告像元数据修复（2026-10-14）

原始影像小于固定 200×170 缩略网格时，旧实现会生成空聚合块并写入 0。
例如 gpu208 上 51×40 的影像在报告中出现约 96% 的零值格子，点击后
反射率和场景参数均显示为 0，且被误判为水体或裸土。

修复后缩略网格不超过原图尺寸。聚合使用一致的有效像元掩码，保留真实的
零标准差、零土壤参数；无数据值输出 JSON null，页面显示“未参与反演”。
坐标、分辨率、LUT 条目数及参数支持范围读取真实元数据，匹配质量区分
MSE 与 RMSE，零匹配误差按有效的最佳匹配处理。

`scripts/refresh_lai_reports.py` 可将已有报告的有效观测从旧网格中恢复，
更新其模板并保留原 Artifact URL、LAI 统计及 GeoTIFF。它不重新反演。
如果已有工作流保留了反射率 GeoTIFF，修复工具会读取其真实空间元数据。
没有记录的数据会明确标注未记录，不填入示例值。

先省略 `--apply` 查看范围，再执行修复：

```bash
python -m scripts.refresh_lai_reports \
  --reports-dir /path/to/reports --backup-dir /path/to/new-backup \
  --db /path/to/ktp_v2_runtime.sqlite3 --artifact-root /path/to/artifacts --apply
```

每份旧 HTML 和对应 Artifact 元数据先备份，再更新摘要、大小和版本。
修复后重启后端以刷新产物缓存。已修复的报告再次运行时跳过。

验证覆盖小影像、无数据、NaN/Infinity、真实零值、旧报告恢复与幂等。
浏览器点击检查覆盖有效像元的五波段和四个场景参数，以及无数据提示。

已同步 gpu208，本地及服务器相关测试均为 47 passed。服务器修复 11 份
已有报告，9 个已登记的原 Artifact URL 登录后验证为 HTTP 200，保留原
LAI 均值、中位数、最小值、最大值和全部有效观测。页面、登录、健康检查
及用户服务正常。验收记录见 `../deploy/lai_report_pixel_validation.json`。
备份位于 `/home/D/zhanghuaxiang_D/apps/ktp/releases/lai-report-pixels-20261014-01`。
