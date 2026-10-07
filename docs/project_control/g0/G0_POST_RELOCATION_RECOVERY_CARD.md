# G0 搬迁后恢复卡（待 Tony 批准；在 g0_relocate.sh 实跑 PASS 之后执行）

```text
TASK_ID   = AI_THEME_APP_G0_POST_RELOCATION_RECOVERY
OWNER     = Tony     EXECUTOR = Mac 本机 Claude Code     DRAFTER = Mira（2026-10-07 22:00）
目标      = 从新的唯一工作区 /Users/admin/Desktop/ai_theme_app（main@ddc9442）恢复 SPS 8090、web_app 8000、前端 5173，
            放回 jyhf 运行状态，由 Tony 在 UI 中拉起采集。截止时间：10/9 开市前
禁止      = 改代码、改数据库密码（Tony：密钥轮换暂缓）、建分支或 worktree、读取或打印环境变量、自行在 UI 中启动采集
```

## 依据（main@ddc9442 中的代码，已核对）

- 3 个 screen 会话（`ai_theme_sps_8090`、`ai_theme_web_8000`、`ai_theme_frontend_5173`）都由 `scripts/start_new_chain_stack_detached.sh` 启动。
  - 这个脚本的 `ROOT_DIR` 取**脚本自己所在的仓库**，所以搬迁后会自动指向桌面。
  - 它会 `source` 仓库根目录下的 `.env.theme` 和 `.env`。这两个文件已由 Tony 复制进 glm，搬迁时会随仓库一起过去。
  - 它会检查 SPS 的运行环境：解释器必须来自 `theme_matcher_env`；`cwd` 和仓库根目录必须等于 ROOT_DIR；`git_sha` 必须等于 HEAD；`git_dirty` 必须为 False。
- web_app 的解释器取 `WEB_PYTHON`，默认是 `<仓库>/.venv/bin/python`，而桌面仓库里没有 `.venv`，所以**必须显式指定**。SPS 默认就用 `theme_matcher_env`。
- jyhf 由 web_app 的 `JyhfCdpManager` 拉起，解释器依次取 `PYTHON` → `CONDA_PYTHON` → `.venv`。按 P1 的决定，**通过 `PYTHON` 显式指定**。

## 步骤

| 步 | 动作 | 验收 / STOP |
|---|---|---|
| R-0 | 确认 `g0_relocate.sh` 实跑结果为 PASS；`git -C /Users/admin/Desktop/ai_theme_app status --porcelain` 为空；`worktree list` 只有 1 行 | 任何一项不满足就 STOP |
| R-1 | 放回 jyhf 运行状态（不覆盖已有文件）：<br>`mkdir -p /Users/admin/Desktop/ai_theme_app/tmp/realtime`<br>`cp -Rn /Users/admin/ai_theme_app_g0_staging_20261007/jyhf_runtime/tmp/realtime/jyhf_cdp_service /Users/admin/Desktop/ai_theme_app/tmp/realtime/` | 49 个文件与暂存目录 `diff -rq` 一致；`seen_keys.json` 的 SHA256 = `9df730d9ac5ccfeae33fee336b69a3a963abec228e46fefe171ac03d979fd97f`；`git status --porcelain` 仍为空（`tmp/` 是被忽略的） |
| R-2 | 确认端口空闲：`lsof -nP -iTCP -sTCP:LISTEN \| grep -E ':(8000\|8090\|8095\|5173) '` | 无输出；有输出就 STOP 并报告 |
| R-3 | **Tony 批准后**由执行会话启动：<br>`cd /Users/admin/Desktop/ai_theme_app`<br>`WEB_PYTHON=/opt/miniconda3/envs/theme_matcher_env/bin/python PYTHON=/opt/miniconda3/envs/theme_matcher_env/bin/python bash scripts/start_new_chain_stack_detached.sh` | 脚本输出中有 `[ok] SPS runtime guard passed`，以及各服务的 ready；有任何 `[fail]` 就 STOP，并原样报告 |
| R-4 | 只读核对（不读环境变量）：<br>`screen -ls`（3 个会话）<br>`lsof -a -p <8090/8000 的 pid> -d cwd`（应为 `/Users/admin/Desktop/ai_theme_app`）<br>`ps -o pid,command= -p <pid>`（解释器应来自 `theme_matcher_env`）<br>`curl -s 127.0.0.1:8090/healthz`（只看 runtime_profile、python、cwd、git_sha、git_dirty 这几个字段） | 全部符合 |
| R-5 | **Tony 打开前端页面**，确认界面正常 | Tony 口头确认 |
| R-6 | **Tony 在 UI 控制台中拉起 jyhf 采集**，PUSH_DB / PUSH_INTEL 按平时的设置 | — |
| R-7 | 只读核对 jyhf：`curl -s 127.0.0.1:8095/status`（`running`、`collector_state`、`cdp_connected`）；`lsof -a -p <8095 的 pid> -d cwd` = 桌面仓库；`ps -o command=` 中的解释器来自 `theme_matcher_env` | 如果解释器不是 `theme_matcher_env`（说明 `PYTHON` 没有传进 screen），报告给 Tony，**不要自行重启** |
| R-8 | 回到搬迁卡的 §8 验收：worktree 只有 1 个、main 与 origin 一致、glm 目录不存在、本地旧分支已删除 | 全部为真 = G0 PASS |

## 回滚

- 服务起不来：先 STOP 并报告，不要回滚仓库。代码与搬迁前完全一致，问题通常出在环境或路径上，交给 Tony 判断。
- 需要退回仓库原状时：由 Tony 本人运行 `g0_rollback.sh`。

## 报告格式

```text
[R-1] 放回的文件数、seen_keys 哈希
[R-2] 端口检查的输出
[R-3] 启动脚本的完整输出
[R-4] 各服务的 PID、cwd、解释器、healthz 的关键字段
[R-7] jyhf 状态（在 Tony 拉起采集之后）
[R-8] G0 最终验收逐项结果
STATUS = PASS / BLOCKED_<原因>
```
