# G0 任务卡 v2：ai_theme_app 唯一工作区

```text
TASK_ID        = AI_THEME_APP_G0_SINGLE_WORKSPACE_P0
CARD_VERSION   = v2.1（2026-10-07 12:30，Mira 起草；加入 Tony 12:27 的边界规定）
OWNER          = Tony（所有决定只由 Tony 作出）
EXECUTOR       = Tony Mac 本机上的 Claude Code 会话
REVIEWER       = ChatGPT（只做审查）
PRIORITY       = P0
```

> **一句话**：保存桌面工作区里没进 git 的内容 → 移除桌面的链接 worktree → 把 main 仓库整体搬到桌面 → glm 目录消失。**本卡不改任何代码，不开任何分支。** 遇到 STOP 条件立刻停下，原样报告。

**v1 → v2 的变化**：
- 删除所有 Julia_core 相关内容：Julia_core 不在本项目范围内，由它自己的流程处理；
- 正式运行路径的核查（原 G0-B）已经完成，记录在 §2。

---

## 会话边界（Tony，2026-10-07 12:27，优先于本卡其他所有条款）

1. 只在 `/Users/admin/glm-workspace/ai_theme_app` 内工作；对桌面工作区 `/Users/admin/Desktop/ai_theme_app`，只允许只读盘点，以及 §4、§6 中明确授权的操作。
2. **不得进入、读取、写入或切换 Julia_core / Julia-AI-Assistant 的任何工作区和分支。** 如果当前目录在 Julia_core 里，立刻离开，不做任何操作。
3. Julia_core 中写死的桌面路径由 Julia_core 那条线负责。本卡只提供 ai_theme_app 搬迁后的**目标路径**和**时间点**，见 §5.5。
4. **搬迁闸门**：§6（移除桌面 worktree）和 §7（搬迁）开始之前，必须先通知 Tony，并等 Tony 确认“Julia_core 线已完成路径封闭”。没有得到确认就 STOP：`AWAITING_JULIA_CORE_PATH_CLOSURE`。
5. §5 中的第 3、4 项检查（`lsof` 以及 launchd / `~/.julia_ops/bin` 的 grep）只读系统级的进程和配置，不进入任何 Julia 工作区。如果 Tony 认为这也越界，就把这两项交给 Tony 本人执行，执行会话跳过。

## 0. 授权范围

| 项 | 授权 |
|---|---|
| 任何仓库的代码、测试、策略、数据库 | **不授权** |
| 新建分支、新建 worktree、新 clone | **禁止** |
| 开发总计划 P0-A | **不授权** |
| 删除 `/Users/admin/Desktop/ai_theme_app` 这个链接 worktree | 授权，但只能用 `git worktree remove`，不加 `--force`，并且满足 §6 的前提 |
| 移动 `/Users/admin/glm-workspace/ai_theme_app` → `/Users/admin/Desktop/ai_theme_app` | 授权，满足 §5、§6 的前提 |
| 删除本地分支 `feature/ai-theme-julia-domain-adapter-v1` | 授权，只能在再次确认远端存档之后 |

### 永久禁止的命令

```text
ps eww / ps e / env / printenv / set -x / launchctl print / cat /proc/*/environ
cat ~/.julia_ops/brain.env，以及任何会显示 brain.env 内容的命令
git worktree prune / git worktree remove --force / git clean -fd / git clean -fdx
git reset --hard / git push --force / rm -rf 任何仓库目录
git merge feature/ai-theme-julia-domain-adapter-v1 / cherry-pick 旧提交
```

---

## 1. 开工前 Owner 必须先填的决定

没填就 STOP：`BLOCKED_OWNER_DECISION_<编号>`。

| # | 决定 | 选项 | Tony 的选择 |
|---|---|---|---|
| **D1** | 桌面工作区里的 `tmp/analyst_workbench/`（63 天工作台数据，git 忽略的文件）。删 worktree 时，这些文件会**和目录一起被删掉** | **A**：打包归档到暂存目录，不进 git<br>**B**：不要了 | **☑ A（Tony，12:27）** |

---

## 2. 已完成的部分（执行者只核对，不重做）

| 项 | 状态 | 证据 |
|---|---|---|
| 远端存档 | ✅ 2026-10-07 12:12，Tony 推送 | `refs/heads/archive/julia-domain-adapter-v1-20261007` = `e1f1b9ad1e44af0edaba9543bc4868ae42f2382f` |
| 桌面 iCloud | ✅ Tony 已关闭 iCloud 云盘 | §5 复核 |
| 正式 18089 不依赖桌面和 glm | ✅ 三条证据一致 | ① 静态：正式入口只绑定 `market_public`，旧 MCP 路径没有调用方；② 现场：工作目录 = `rd1_v1/assistant`，`lsof` 中桌面和 glm 的命中数都是 0；③ 日志：`brain-18089.{out,err}.log` 中旧路径的命中数都是 0（err.log 从 10/1 起才有记录）|

**由此得出**：移除桌面 worktree、搬迁 glm 目录，都**不会**影响正式 Julia。

**残留风险**：Julia_core 里仍然写死着桌面路径，目前没有调用方。搬迁之后，桌面会变成你天天开发的 main 工作区；如果日后有人重新接回这条旧路径，正式进程就会读到开发代码。本卡不处理这个风险，由 Julia_core 那条线负责。按会话边界第 4 条，§6 和 §7 必须等那条线完成路径封闭之后才能做。

---

## 3. G0-0：基线核对（只读）

在本机执行，逐条记录输出。

```bash
export GIT_OPTIONAL_LOCKS=0
A=/Users/admin/glm-workspace/ai_theme_app
D=/Users/admin/Desktop/ai_theme_app

git -C $A rev-parse --abbrev-ref HEAD                         # 期望 main
git -C $A fetch origin
git -C $A rev-parse main origin/main                          # 期望两个都是 ddc9442e88c5bf6f5248bfb141e74472c48eb25a
git -C $A status --porcelain | wc -l                          # 期望 0
cat $D/.git                                                   # 期望 gitdir: …/glm-workspace/ai_theme_app/.git/worktrees/ai_theme_app
git -C $D rev-parse --abbrev-ref HEAD HEAD                    # 期望 feature/ai-theme-julia-domain-adapter-v1 / e1f1b9ad…
git -C $A ls-remote origin refs/heads/archive/julia-domain-adapter-v1-20261007   # 期望 e1f1b9ad…
git -C $A worktree list --porcelain
```

**STOP 条件**：任何一个 SHA、分支或指针关系与期望不符，结果为 `BLOCKED_BASELINE_DRIFT`。不许自行调整任务去适应。

---

## 4. G0-A：保存桌面工作区里没进 git 的内容

### 4.1 盘点（只读）

```bash
cd /Users/admin/Desktop/ai_theme_app
git status --porcelain                      # 已跟踪文件的改动
git diff --stat; git diff --cached --stat
git ls-files --others --exclude-standard    # 未跟踪的文件
git ls-files --others --ignored --exclude-standard --directory | awk -F/ '{print $1"/"$2}' | sort | uniq -c
#   ↑ 被忽略的文件只列目录名和数量，不打开任何文件内容（里面可能有 .env）
```

### 4.2 分类规则

| 类别 | 处理 |
|---|---|
| `docs/project_control/`、`docs/strategy_model/` 下的审计、计划、策略模型文档，以及 TSV 清单 | **保存**到暂存目录 |
| 按 D1 选 A：`tmp/analyst_workbench/` | 打成 `tar.gz` 放进暂存目录，并记录 SHA256 |
| `.env`、各种密钥文件 | **不复制，也不打开**。报告文件名，并确认主仓库里有对应的配置。如果主仓库没有对应配置，STOP：`BLOCKED_ENV_FILE_ONLY_IN_DESKTOP` |
| 日志、缓存、`__pycache__`、`node_modules`、构建产物 | 不保存 |
| **已跟踪文件有改动**，或者有**未跟踪的代码文件**（`.py`、`.ts`、`.tsx`、`.sql`、`.sh` 等） | STOP：`BLOCKED_UNTRACKED_ENGINEERING_STATE`，列出清单，等 Tony 判断 |

### 4.3 复制并校验

```text
暂存目录 = /Users/admin/ai_theme_app_g0_staging_20261007
          （在两个仓库之外；不存在就新建，已存在就 STOP 报告）
清单     = <暂存目录>/MANIFEST.tsv，列为：相对路径、大小、SHA256、源路径、暂存路径
```

复制完成后，重新计算每个文件的 SHA256，并与源文件逐一比对。只要有一个对不上，就 STOP：`BLOCKED_STAGING_HASH_MISMATCH`。

**注意**：本步骤只**复制**，不从桌面工作区移走任何文件。移走放到 §6。

---

## 5. G0-B：搬迁前的安全检查

```bash
# 1. 桌面不在 iCloud 同步里
ls ~/Library/Mobile\ Documents/com~apple~CloudDocs/ 2>/dev/null | grep -E "^(Desktop|桌面)$"   # 期望无输出
# 2. 两个目录在同一个卷上（mv 是原子重命名，不是先复制再删除）
df /Users/admin/Desktop /Users/admin/glm-workspace | awk 'NR>1{print $1}' | sort -u | wc -l    # 期望 1
# 3. 没有进程正在使用 glm 目录
lsof 2>/dev/null | grep "/glm-workspace/ai_theme_app" | awk '{print $1, $2}' | sort -u           # 期望无输出
# 4. 没有服务配置写着 glm 路径
grep -rl "glm-workspace/ai_theme_app" ~/Library/LaunchAgents ~/.julia_ops/bin /Library/LaunchDaemons 2>/dev/null
crontab -l 2>/dev/null | grep -c "glm-workspace/ai_theme_app"
# 5. 仓库里有没有虚拟环境（venv 内部写死了绝对路径，搬家后会失效）
ls -d /Users/admin/glm-workspace/ai_theme_app/{.venv,venv,env} 2>/dev/null
```

| 检查结果 | 处理 |
|---|---|
| 第 1 项有输出 | STOP：`BLOCKED_DESKTOP_STORAGE_UNSAFE` |
| 第 2 项不等于 1 | STOP：`BLOCKED_CROSS_VOLUME_MOVE` |
| 第 3 项有输出（比如 SPS API、W2S 预警循环正在从 glm 运行） | STOP：`BLOCKED_SERVICES_RUNNING_FROM_GLM`。列出进程名和 PID，等 Tony 安排停服窗口。**不许自己停服务** |
| 第 4 项有命中 | STOP：`BLOCKED_SERVICE_CONFIG_REFERENCES_GLM`。列出文件，等 Tony 决定怎么改 |
| 第 5 项有 venv | 记录下来。搬家后按 §7 重建，**不许**复制或修补 venv |

---

### 5.5 通知 Tony，等待搬迁闸门

§3 到 §5 完成后，执行会话交一份**中间报告**（[1] 到 [3]），然后停下。报告里写明交给 Julia_core 线的信息：

```text
AI_THEME_APP_TARGET_PATH  = /Users/admin/Desktop/ai_theme_app（与现在的路径相同，但内容会从旧功能分支 e1f1b9ad 变成 main@ddc9442 或之后的 main）
WORKTREE_REMOVAL          = 在 Tony 确认之后。移除到搬迁完成的这段时间里，这个路径会短暂不存在
RELOCATION_DONE           = 由执行会话在 §7 完成时报告确切时间
AFTER_RELOCATION          = 这个路径下不再有 mcp_server/、strategy_knowledge/、tmp/analyst_workbench/
```

状态：`AWAITING_JULIA_CORE_PATH_CLOSURE`。等 Tony 明确说“继续”之后，才能进入 §6。

---

## 6. G0-C：移除桌面的链接 worktree

**前提，缺一不可**：§3 基线通过；§4 暂存校验通过；§5 的检查全部通过；**Tony 已确认 Julia_core 线完成路径封闭，并下达“继续”**。

```bash
cd /Users/admin/Desktop/ai_theme_app
git status --porcelain; git diff --stat; git diff --cached --stat; git ls-files --others --exclude-standard
#   ↑ 全部记录。已跟踪文件不能有改动
```

1. 只把 §4 里**已经通过哈希校验**的未跟踪文档从桌面工作区**移**到暂存目录的 `moved/` 下。移完之后，再对每个文件比对一次哈希。
2. `git ls-files --others --exclude-standard` 必须为空，否则 STOP。
3. 执行 `git -C /Users/admin/glm-workspace/ai_theme_app worktree remove /Users/admin/Desktop/ai_theme_app`（**不加 `--force`**）。如果 git 拒绝，STOP，原样报告错误。
4. 核对：`/Users/admin/Desktop/ai_theme_app` 已不存在；`git worktree list` 只剩 glm 一行；`git cat-file -e e1f1b9ad1e44af0edaba9543bc4868ae42f2382f` 仍然成功。

---

## 7. G0-D：把主仓库搬到桌面

```bash
mv /Users/admin/glm-workspace/ai_theme_app /Users/admin/Desktop/ai_theme_app
cd /Users/admin/Desktop/ai_theme_app
test -d .git && echo REAL_GIT_DIR
git rev-parse --show-toplevel                  # 期望 /Users/admin/Desktop/ai_theme_app
git rev-parse --abbrev-ref HEAD                # 期望 main
git fetch origin && git rev-list --left-right --count main...origin/main   # 期望 0	0
git status --porcelain | wc -l                 # 期望 0
git remote get-url origin                      # 期望 https://github.com/tonychang925-dev/ai_theme_app.git
git worktree list --porcelain                  # 期望只有一行，就是桌面
```

- 如果有 venv：在新位置**重建**（按仓库现有的依赖文件），并记录 Python 版本。
- **只在** `git ls-remote` 再次确认存档分支 = `e1f1b9ad…` 之后，才删除本地分支：`git branch -D feature/ai-theme-julia-domain-adapter-v1`。这个分支只在本地，而且已经有远端存档，所以用 `-D`。
- 检查 `/Users/admin/glm-workspace/ai_theme_app` 已不存在。

---

## 8. 最终验收（全部为真才算 PASS）

```text
AI_THEME_APP_LOCAL_WORKSPACE        = /Users/admin/Desktop/ai_theme_app
AI_THEME_APP_.git                   = 真实目录
AI_THEME_APP_WORKTREE_COUNT         = 1
AI_THEME_APP_BRANCH                 = main，与 origin/main 0/0，工作区干净
OLD_FEATURE_HISTORY_REMOTE_ARCHIVED = 是（e1f1b9ad…）
OLD_LOCAL_FEATURE_BRANCH            = 已删除
GLM_AI_THEME_WORKSPACE              = 不存在
AUDIT/PLAN DOCS PRESERVED           = 是（MANIFEST 哈希全部一致）
FORMAL_18089                        = 未重启、未受影响（搬迁前后 PID 相同）
P0-A STARTED                        = 否
```

## 9. 最终报告格式

```text
[1] BASELINE        main / origin/main / 桌面 HEAD / 存档分支 / 18089 的 PID
[2] PRESERVATION    暂存目录、文件数、MANIFEST 的 SHA256、analyst_workbench 打包（如果 D1 选了 A）
[3] PRE-MOVE CHECKS §5 五项检查的原始输出
[4] WORKTREE REMOVAL 移除前的 status、diff 记录，移除后的 worktree list
[5] RELOCATION      新路径的 .git 结构、main 与 origin 的关系、venv 处理
[6] GOVERNANCE      ai_theme_app 本地只在本地的分支（期望 0）
[7] STATUS          PASS，或 BLOCKED_<确切原因>（附停下时的完整现场）
```

每条结论都要附上命令和原始输出。没有证据的 PASS 一律视为 FAIL。
