# KTP 项目约定

## gpu208 同步（用户于 2026-10-14 明确要求）

- 每次完成代码修改并通过相关验证后，必须将本次修改同步到 gpu208；需要更新网页时同时同步前端生产构建产物。同步是任务完成的一部分，用户已持续授权，无需每次重复确认。
- SSH 别名：`kt-server-208`，实际目标：`zhanghuaxiang_D@192.168.9.208`，主机名：`gpu208`。
- 运行源码：`/home/D/zhanghuaxiang_D/Code/KTP`；独立运行资源：`/home/D/zhanghuaxiang_D/apps/ktp`。具体环境与操作见 `docs/kt_server_deployment.md`。
- 同步前检查服务器相关文件，备份本次被覆盖的文件。保留服务端独立修改，不覆盖 `.env`、凭据、数据库、模型或分析产物；前端保留旧哈希资源，最后替换入口 HTML。
- 使用现有 `ktp` Conda 环境。按变更需要执行 `systemctl --user restart ktp-backend ktp-frontend`，验证用户服务、页面、`/health` 及本次涉及的接口。
- 最终回复报告同步与验证结果；连接或验证失败时明确说明未完成，保留备份与回滚信息，不将本地完成误报为服务器已更新。
