# G0 准备：jyhf 事件采集服务迁移方案（待 Tony 批准）

> 起草：Mira，2026-10-07 21:00。全程只读，**没有停止、启动或修改任何进程和文件**。
> 证据来源：`main@ddc9442` 中的代码（`services/jyhf_cdp_service/`、`web_app_service/services/jyhf_cdp_manager.py`、`scripts/start|stop_jyhf_cdp_service.sh`），以及桌面 worktree 的只读盘点、执行会话报告的进程信息。
> 对应闸门：G0 v2.1 卡的闸门 ②——“jyhf 采集服务迁移方案经 Tony 批准，并完成切换”。

---

## 1. 证据

### 1.1 已确认（直接读代码、文件得到）

| # | 事实 |
|---|---|
| J-1 | PID 52169 的启动命令是 `/Users/admin/Desktop/ai_theme_app/.venv/bin/python -m uvicorn services.jyhf_cdp_service.app:app --host 127.0.0.1 --port 8095 --workers 1`，工作目录是桌面 worktree，10/5 09:10 启动，父进程是 1。（来自执行会话报告） |
| J-2 | 采集器已由 Tony 手动停止。状态文件显示 `collector_state: stopped`、`cdp_connected: false`，最后一次抓取在 10/5 09:10:16。8095 端口上运行的只是 HTTP 外壳。 |
| J-3 | `services/jyhf_cdp_service/` 共 16 个文件，桌面版与 `main@ddc9442` **逐文件完全一致**（按 blob 哈希比对）。 |
| J-4 | 服务的数据去向：数据库表 `subject_history_staging`（`JYHF_CDP_PUSH_DB=1` 时写入，SPS 轮询这张表）、Redis `stream:jyhf:feed`（`JYHF_CDP_PUSH_INTEL=1` 时写入）、`theme_data_complete/cdp_events/`（原始事件，两边目前都不存在）。 |
| J-5 | 运行状态保存在 `<项目根>/tmp/realtime/jyhf_cdp_service/`，共 49 个文件、216 KB，其中包括去重记录 `seen_keys.json`（2720 字节，SHA256 `9df730d9…97f`）。日志写在 `<项目根>/logs/jyhf_cdp_service.log`。**项目根 = 服务代码所在的仓库根目录**（`config.py`：`AI_THEME_PROJECT_ROOT`，未设置时为 `parents[2]`）。 |
| J-6 | 运行状态已复制到暂存目录 `jyhf_runtime/tmp/realtime/jyhf_cdp_service/`，并逐文件 diff 校验一致。由于 52169 仍在运行，**这份副本在停服后还要再校验一次，才算最终版本**。 |
| J-7 | 正规的启动途径（`desktop/src/runtime/serviceManager.ts:169–170` 的注释）：**“JYHF CDP must be started only by web_app JyhfCdpManager via the UI console.”** 即只能由 8000 端口的 web_app 在 UI 控制台里拉起。 |
| J-8 | `JyhfCdpManager` 拉起服务的方式：`subprocess.Popen([python, -m uvicorn …:app, --port 8095], cwd=<web_app 所在仓库根>, env=os.environ 复制 + JYHF_CDP_PUSH_INTEL/PUSH_DB/SERVICE_PORT)`。其中 `python` 依次取环境变量 `PYTHON` → `CONDA_PYTHON` → `<仓库根>/.venv/bin/python`。 |
| J-9 | `config.py` **不读 .env 文件**，只读进程的环境变量。数据库连接参数（PG_*）、Redis 参数都**继承自启动它的 web_app 进程**。 |
| J-10 | 桌面的 `.venv` 是基于 `/opt/miniconda3/bin/python3.13`（3.13.5）建立的普通 venv，会随 worktree 一起删除。glm 仓库里没有 `.venv`。 |
| J-11 | `requirements-jyhf-cdp.txt` 只列了 `fastapi`、`uvicorn`、`pydantic`、`websocket-client`，但代码还 import 了 `asyncpg`（db_sink）和 `redis`（intel_pusher）。**这份依赖清单不完整。** |

### 1.2 推断（尚未验证）

| # | 推断 | 依据 |
|---|---|---|
| I-1 | 10/5 09:10 拉起 52169 的，是当时从**桌面 worktree** 运行的 web_app（或者 Tony 手动执行了桌面的 `scripts/start_jyhf_cdp_service.sh`），因为它用的是桌面的 `.venv` 和工作目录 | J-1、J-8 |
| I-2 | 今天被停掉的 glm 版 web_app（PID 46533，`theme_matcher_env`）如果在 UI 里启动 jyhf，会去找 `glm/.venv/bin/python`，而这个文件不存在；除非它的环境里设置了 `PYTHON` 或 `CONDA_PYTHON` | J-8、J-10 |
| I-3 | 52169 进程里的 PG_* 和 PUSH 开关，就是当时那个 web_app 的环境，无法在不读取进程环境变量的前提下核实（读取环境变量是被禁止的） | J-9 |

---

## 2. 方案比较

| | **方案 B（推荐）：在搬迁窗口内一次切换** | 方案 A：先切到 glm，搬迁后再切一次 |
|---|---|---|
| 做法 | 进入 §6 时停掉 52169（外壳）→ 移除 worktree → 搬迁 → 放回运行状态 → 从桌面 main 启动 web_app → 在 UI 控制台里拉起 jyhf | 现在就从 glm 拉起 jyhf → 搬迁后再从桌面重启 |
| 重启次数 | 1 | 2 |
| 采集中断 | **没有**（采集器本来就是 Tony 手动停的） | 没有 |
| 风险 | 低。代码完全一致，只需要准备 Python 环境 | 较高。glm 版运行时的项目根是 glm 路径，搬迁时这个目录会“消失”，状态和日志会写到不存在的路径上；还得在 glm 里多建一次环境 |
| 结论 | ✅ | ❌ |

---

## 3. 方案 B 的切换步骤（待批准；批准前一步都不执行）

**前提**：闸门 ① 已由 Tony 确认；本方案已由 Tony 批准；搬迁脚本的演练（dry-run）通过。

| 步 | 动作 | 执行人 | 验收 |
|---|---|---|---|
| B-0 | 准备 Python 环境（见 §4）。在任意目录用该解释器跑一遍 import 检查 | 执行会话（只建环境，不启动服务） | `import fastapi, uvicorn, pydantic, websocket, asyncpg, redis` 全部成功 |
| B-1 | 先记录停服前的状态：`curl -s 127.0.0.1:8095/status`（只读） | 执行会话 | 保存输出，确认 `collector_state` 为 stopped |
| B-2 | 停服：在桌面 worktree 根目录执行 `scripts/stop_jyhf_cdp_service.sh`（先调用 `/collector/stop`，再按 pidfile 结束进程）；如果 pidfile 不存在，就 `kill -TERM 52169` | **Tony** | `lsof -i :8095` 无监听 |
| B-3 | 对暂存目录中的 `jyhf_runtime` 做最终校验（与桌面源目录 diff，`seen_keys.json` 哈希不变或更新为最终值） | 执行会话 | MANIFEST 更新，哈希一致 |
| B-4 | 执行 G0 §6、§7（移除 worktree、搬迁） | 执行会话 | 见搬迁脚本 |
| B-5 | 放回运行状态：`cp -Rn <暂存>/jyhf_runtime/tmp/realtime/jyhf_cdp_service /Users/admin/Desktop/ai_theme_app/tmp/realtime/`（不覆盖已有文件） | 执行会话 | 49 个文件哈希与暂存目录一致 |
| B-6 | 从桌面 main 启动 web_app（8000），并显式设置 `PYTHON=<§4 选定的解释器>`；SPS（8090）和前端（5173）按原来的方式启动 | **Tony**（或由 Tony 授权的“搬迁后恢复卡”） | `/health` 正常 |
| B-7 | 是否在 UI 控制台里拉起 jyhf，以及 PUSH_DB / PUSH_INTEL 开关如何设置，**由 Tony 决定**（采集器原本就是停着的） | **Tony** | `/status` 中 `running: true`；采集器状态符合 Tony 的选择 |
| B-8 | 核对：新进程的工作目录 = `/Users/admin/Desktop/ai_theme_app`，解释器 = §4 选定的解释器 | 执行会话（`lsof -a -p <pid> -d cwd`、`ps -o command=`，不读取环境变量） | 记录进报告 |

---

## 4. Python 环境：两个选项（请 Tony 选）

| 选项 | 做法 | 优点 | 缺点 |
|---|---|---|---|
| **P1（推荐）** | 复用 conda 的 `theme_matcher_env`（SPS 和 web_app 原本就用它）。启动 web_app 时设置 `PYTHON=/opt/miniconda3/envs/theme_matcher_env/bin/python` | 不用新建环境；三个服务用同一套解释器 | 需要先确认它装了 `websocket-client`、`asyncpg`、`redis`。缺的话，往这个共享环境里安装前要经 Tony 批准 |
| P2 | 搬迁后在桌面根目录重建 `.venv`：`/opt/miniconda3/bin/python3.13 -m venv .venv`，再安装 `requirements-jyhf-cdp.txt` 以及 `asyncpg`、`redis` | 与原来的 52169 完全同构 | 多维护一个环境；`requirements-jyhf-cdp.txt` 需要补全（这是代码改动，本卡不做，只能在安装时手动补上） |

只读检查（执行会话现在就可以做）：
```bash
/opt/miniconda3/envs/theme_matcher_env/bin/python -c "import fastapi, uvicorn, pydantic, websocket, asyncpg, redis; print('OK')"
```

---

## 5. 回滚

- 代码层面不需要回滚：main 中的代码与旧版完全一致。
- 新环境启动失败时：按 §4 换用另一个选项；**不要**去恢复旧 worktree。
- 运行状态有问题时：从暂存目录重新放回 `jyhf_runtime`，暂存副本只读，保持不变。

## 6. 需要 Tony 决定

1. 是否批准方案 B；
2. Python 环境选 P1 还是 P2；
3. 切换后是否启动采集器，以及 PUSH_DB / PUSH_INTEL 两个开关怎么设。

---

## 7. Tony 的决定（2026-10-07 21:36）

| 决定 | 结论 |
|---|---|
| 方案 | **方案 B**（在搬迁窗口内一次切换） |
| Python 环境 | **P1**：复用 `theme_matcher_env`，**必须通过 `PYTHON=/opt/miniconda3/envs/theme_matcher_env/bin/python` 显式指定**，不依赖默认回退。`requirements-jyhf-cdp.txt` 漏掉的 `asyncpg`、`redis` 另开小卡补上（那是代码改动，不在 G0 范围内） |
| 启动顺序 | 先启动 web_app，确认界面正常，再在 UI 里拉起采集。PUSH_DB / PUSH_INTEL 按 Tony 平时的设置。**截止时间：10/9 开市前跑通一次**，不必当晚完成 |
| 演练 | 批准执行会话在 ai_theme_app 以外的目录中，对两个脚本各演练一次 |
