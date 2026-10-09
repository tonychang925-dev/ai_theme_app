# G0 结案记录：ai_theme_app 唯一工作区

> **STATUS = PASS**（2026-10-07 22:02）。执行会话为 Tony Mac 本机上的 Claude Code；Mira 负责起草和对照核对；所有决定由 Tony 作出。

## 最终状态

| 项 | 值 |
|---|---|
| 唯一工作区 | `/Users/admin/Desktop/ai_theme_app`，`.git` 为真实目录，worktree 数量 = 1 |
| 分支 | 只有 `main` @ `ddc9442e88c5bf6f5248bfb141e74472c48eb25a`，与 origin/main 领先 0、落后 0，工作区干净 |
| 远端存档 | `archive/julia-domain-adapter-v1-20261007` = `e1f1b9ad…`；`archive/post-market-decision-v2-pr14f-20261007` = `0268f1f6b6d6…` |
| glm 路径 | `/Users/admin/glm-workspace/ai_theme_app` 已不存在。Claude 虚拟机重建的空挂载点已用 `rmdir` 删除 |
| 服务（都从桌面仓库运行，解释器都是 `theme_matcher_env`） | SPS 8090、web_app 8000、前端 5173（screen 会话）；jyhf 8095 由 web_app 拉起，采集运行中，`cdp_connected=true` |
| 暂存目录 | `/Users/admin/ai_theme_app_g0_staging_20261007`：MANIFEST 79 行，哈希全部一致；另有 `moved_20261007_215151/`（1947 个文件）、`scripts/`、两份演练日志和一份实跑日志 |

## 过程中的偏差和说明

- 18089 的 PID 由 70567 变为 24978，是 Julia_core 线 #246 部署时重启造成的，Tony 已确认，与 G0 无关。
- 启动脚本汇总里的 `[fail] web_app workspace chain`，是冷启动后第一次查询超过 3 秒；之后再请求返回 200。
- Mira 两次把要交给执行会话的文件（脚本、恢复卡）只发到对话里，没有写到 Mac 上，导致执行会话报告 `NOT_FOUND`。之后改为直接写入暂存目录的 `scripts/`，并附上哈希。
- 虚拟机 81119 仍持有一个指向已删除目录的只读句柄，无害，应用重启后会消失。

## 遗留项（不在 G0 范围内，由 Tony 决定）

1. 是否清理 `ai_theme_app_PRE_A3_20261004`（2.6G）及其登记的 `ai_theme_app_market_r11_f1bc3de`。它的 3 个产物、3 条 stash 补丁已存进暂存目录，pr14f 已在远端存档。
2. 8000 端口目前绑定在所有网卡（0.0.0.0），是否改为只监听本机。
3. `requirements-jyhf-cdp.txt` 漏掉了 `asyncpg`、`redis`。这是代码改动，按“Agent 不得建分支”的规定，需要由 Tony 决定走哪条路径。
4. “禁止 Agent 建分支”的硬限制，四层方案中采用哪几层。
5. SPS 启动后，W2S 预警循环随之恢复，状态与搬迁前一致。是否关闭是 Tony 的运维决定。
6. 暂存目录确认无误后再决定是否清理。在此之前保留。
