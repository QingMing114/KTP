# kt-server 用户目录部署

部署日期：2026-10-13。目标 SSH：`zhanghuaxiang_D@192.168.9.208`，已验证密钥认证。

| 项目 | 配置 |
| --- | --- |
| 页面入口 | http://192.168.9.208:3002 |
| 源码 | `/home/D/zhanghuaxiang_D/Code/KTP` |
| 独立 Conda 环境 | `/home/D/zhanghuaxiang_D/.conda/envs/ktp`，环境名 `ktp` |
| 运行版本 | Python 3.11、Node.js 22 |
| 私有数据与模型 | `/home/D/zhanghuaxiang_D/apps/ktp` |
| 后端 | `127.0.0.1:8005`，由 3002 页面服务代理 |
| 用户服务 | `ktp-backend.service`、`ktp-frontend.service` |
| 页面管理员 | `zhanghuaxiang_D` |

服务使用独立环境的绝对解释器路径和 PATH。已启用两个用户服务及 `Linger=yes`，退出 SSH 后继续运行，开机由用户服务管理器启动。未改动服务器上的其他项目、环境或服务。

服务器的共享 `/tmp` 当前缺少目录执行权限，本项目使用私有 `apps/ktp/tmp` 作为 `TMPDIR`，避免依赖该目录。服务安装脚本会配置它；命令行构建与检查时也需导出下述变量。

## 登录与日常操作

```bash
ssh zhanghuaxiang_D@192.168.9.208
source /opt/anaconda3/etc/profile.d/conda.sh
conda activate ktp
export TMPDIR=/home/D/zhanghuaxiang_D/apps/ktp/tmp
cd /home/D/zhanghuaxiang_D/Code/KTP

systemctl --user status ktp-backend ktp-frontend
systemctl --user restart ktp-backend ktp-frontend
journalctl --user -u ktp-backend -u ktp-frontend -n 100 --no-pager
curl --fail http://127.0.0.1:3002/health
```

管理员初始随机密码只保存在服务器的私有文件中：

```bash
cat /home/D/zhanghuaxiang_D/apps/ktp/credentials/admin-password
```

该文件权限为 600，凭据目录权限为 700。`backend/.env` 权限为 600，内含本实例独立的认证及许可证签名密钥；模型连接沿用项目既有配置。密码、令牌、机器许可证和私有配置不进入 Git。

## 源码与运行数据

`backend/var` 链接到 `apps/ktp/var`。SQLite 数据库、登录用户和分析产物位于 `var/data`、`var/artifacts`；模型与 LUT 位于 `models`；生成的 HTML 报告位于 `reports`；部署验收产物位于 `validation`。

已配置的外部资源：

- `LAI_LUT_PATH`：`models/LUT_test.txt`。
- `LAI_REPORT_TEMPLATE_PATH`：仓库的 `backend/v2/tools/templates/lai_report_v3.html`。
- `CROP_CLASSIFIER_MODEL_PATH`：`models/kdd2020_spatial_vgg16_rgb224_6class_0b9f40f6.h5`，已校验 SHA-256。
- `CROP_CLASSIFIER_PYTHON`：独立环境的 Python，使用 TensorFlow CPU 推理。
- `APSIM_DEMO_DB`：`models/GxExM.db`，来自既有 APSIM Wheat 验证输出，用于生成报告。
- `LAI_REPORT_OUTPUT_DIR` 与 `APSIM_REPORT_OUTPUT_DIR`：均为本实例的 `reports` 目录，生成与读取共用该目录。

APSIM 子模块已检出仓库固定版本。本机已接通小麦/玉米模拟估产报告以及已有 APSIM 验证输出的报告；尚未安装用于新模拟的 APSIM `Models` 可执行程序。模拟演示明确标注数据来源，不代表当前地块的实际产量。

## 环境安装记录

```bash
env CONDA_PKGS_DIRS=/home/D/zhanghuaxiang_D/conda-pkgs \
  /opt/anaconda3/bin/conda create \
  --prefix /home/D/zhanghuaxiang_D/.conda/envs/ktp \
  --override-channels -c conda-forge python=3.11 pip nodejs=22 -y

source /opt/anaconda3/etc/profile.d/conda.sh
conda activate ktp
cd /home/D/zhanghuaxiang_D/Code/KTP
mkdir -p /home/D/zhanghuaxiang_D/apps/ktp/tmp
export TMPDIR=/home/D/zhanghuaxiang_D/apps/ktp/tmp
python -m pip install -e 'backend[dev]' -r deploy/requirements-cpu.txt
python -m pip check
git submodule update --init --depth 1
cd frontend
npm ci
npm run build
```

模型权重、LUT 和 APSIM 验证数据库是独立部署资源，不随 Git 下载。安装用户服务之前，需要准备私有 `.env`、上述资源和管理员密码文件。现有配置已完成准备；以下脚本可以重复执行，保留已有账户并校验资源：

```bash
cd /home/D/zhanghuaxiang_D/Code/KTP
python deploy/install_user_services.py \
  --app /home/D/zhanghuaxiang_D/Code/KTP \
  --data-dir /home/D/zhanghuaxiang_D/apps/ktp \
  --admin-user zhanghuaxiang_D
systemctl --user restart ktp-backend ktp-frontend
loginctl show-user zhanghuaxiang_D -p Linger
```

## 更新与验收

用户于 2026-10-14 要求：以后每次代码修改完成并通过验证，都同步至本 gpu208 实例。该要求已经写入项目 `AGENTS.md`，同步及运行验收属于任务完成条件。

本地工作树存在尚未提交的修改时，不能仅使用 `git pull`。应校验并备份服务器将被覆盖的文件，只传输本次修改及所需前端构建产物；不覆盖私有配置与运行数据。前端保留旧哈希资源，先上传新资源，最后替换 `frontend/dist/index.html`。后端变更需重启用户服务以重新加载代码和示范农场 GeoJSON。同步后检查文件哈希、服务状态、页面及相关接口。

```bash
cd /home/D/zhanghuaxiang_D/Code/KTP
export TMPDIR=/home/D/zhanghuaxiang_D/apps/ktp/tmp
git pull --ff-only
git submodule update --init --depth 1
python -m pip install -e 'backend[dev]' -r deploy/requirements-cpu.txt
cd frontend
npm ci
npm run build
systemctl --user restart ktp-backend ktp-frontend
curl --fail http://127.0.0.1:3002/health
```

前端已兼容内网 HTTP IP 访问时缺少 `crypto.randomUUID` 的浏览器环境。

以下验收脚本使用服务器私有密码文件登录，不打印密码或令牌；它会建立专用验收会话和模拟演示任务，调用一次真实模型，并执行 LAI、作物模型及 APSIM 报告检查：

```bash
cd /home/D/zhanghuaxiang_D/Code/KTP
python deploy/user_server_smoke.py \
  --app /home/D/zhanghuaxiang_D/Code/KTP \
  --data-dir /home/D/zhanghuaxiang_D/apps/ktp \
  --admin-user zhanghuaxiang_D
```

结果写入 `apps/ktp/validation/live-smoke-result.json`。LAI 与作物识别使用专门标记的合成影像验证计算链路，未验证实测精度。部署验收摘要见 `deploy/kt_server_validation.json`。
