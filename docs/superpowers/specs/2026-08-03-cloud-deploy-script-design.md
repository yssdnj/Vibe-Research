# 云服务器一键部署脚本设计

## 目标

在 Linux 云服务器的 Vibe-Research 项目根目录运行：

```bash
chmod +x deploy.sh && ./deploy.sh
```

脚本完成 Codex CLI 登录检查、依赖安装，以及前后端后台启动。部署后通过 `http://<服务器地址>:5899` 访问前端。

## 前提与范围

- 使用系统 `python3` 和 `pip3`，不创建虚拟环境。
- 使用系统 Node.js、npm 和 Bash。
- 云服务器允许交互式终端登录，Codex 首次登录由用户在终端完成。
- 前端使用 Vite 开发服务器对外提供服务；这是简易部署方案，不包含 Nginx、TLS 或域名配置。
- 脚本不自动修改云厂商安全组或系统防火墙。

## 命令接口

```bash
./deploy.sh           # 首次部署或启动
./deploy.sh status    # 显示前后端状态
./deploy.sh logs      # 持续查看前后端日志
./deploy.sh stop      # 停止前后端
./deploy.sh restart   # 重启前后端
```

## 首次部署流程

1. 确认脚本从项目根目录运行，并检查 `backend/requirements.txt` 与 `frontend/package.json`。
2. 检查 `python3`、`pip3`、`node`、`npm` 和 `nohup`。缺失时给出明确错误并退出。
3. 检查 `codex` 命令。缺失时使用 `npm install -g @openai/codex` 安装。
4. 执行 `codex login status`：已登录则继续；未登录则执行交互式 `codex login`，登录失败时停止部署。
5. 执行 `python3 -m pip install -r backend/requirements.txt` 和 `npm install --prefix frontend`。
6. 创建项目根目录 `.run/`，用于 PID 与日志文件。
7. 使用 `nohup` 启动后端：工作目录为 `backend/`，命令为 `python3 -m uvicorn app:app --host 0.0.0.0 --port 8900`。
8. 使用 `nohup` 启动前端：工作目录为 `frontend/`，命令为 `npm run dev -- --host 0.0.0.0 --port 5899`。
9. 写入 PID 文件，短暂检查进程是否仍存活；失败时显示对应日志尾部并返回非零状态。
10. 输出前端地址、后端健康检查地址、PID 和日志路径。

## 进程与日志管理

- `.run/backend.pid` 与 `.run/frontend.pid` 保存进程 PID。
- `.run/backend.log` 与 `.run/frontend.log` 保存标准输出和错误输出。
- 启动前通过 PID 文件和 `kill -0` 检查进程，避免重复启动。
- `stop` 只终止 PID 文件记录且仍存活的进程，不使用宽泛的 `pkill`。
- PID 已失效时清理对应 PID 文件，不影响其他 Python、Node 或 Vite 进程。
- `logs` 同时跟踪两个日志；不存在的日志先创建为空文件。

## Codex 登录行为

- 只有 `codex login status` 返回未登录时才调用 `codex login`。
- 登录过程保持前台交互，完成后才安装依赖并启动服务。
- 后端继承脚本当前环境和用户的 `~/.codex` 登录状态。
- 以其他 Linux 用户运行后端时，不保证能够读取当前用户的 Codex 登录状态。

## 公网与安全边界

- 前后端分别监听 `0.0.0.0:5899` 和 `0.0.0.0:8900`。
- 脚本支持读取调用者预先设置的 `VR_API_KEY`、`VR_ALLOW_ORIGINS` 等环境变量，但不把密钥写入仓库。
- 未设置 `VR_API_KEY` 时打印醒目的公网无鉴权警告，但按照已确认的简易部署需求继续启动。
- 用户需自行在安全组开放 5899 和 8900；生产环境后续应迁移到 Nginx、HTTPS，并把后端限制为本机监听。

## 错误处理与兼容性

- 使用 `set -Eeuo pipefail`，关键步骤失败即停止。
- 支持常见 Linux Bash 环境，不针对 PowerShell 或 Windows。
- 所有路径从脚本自身位置解析，因此可从其他工作目录调用。
- 路径引用始终加引号，以支持项目路径包含空格。

## 验证

- 静态语法检查：`bash -n deploy.sh`。
- 使用临时 PATH 与伪命令测试依赖缺失、Codex 已登录/未登录、重复启动、停止和状态逻辑，避免测试时真的安装包或启动公网服务。
- 验证项目现有后端测试、前端测试与前端构建不因脚本新增而回归。

