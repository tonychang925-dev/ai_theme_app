# Julia Core / RD1 开发宪法

## 十条军规 — 违反即终止

**状态：最高工程纪律**  
**适用范围：所有 Agent、Codex、Claude、Mira、人工开发者、Review Agent、自动化任务，以及 Julia Core / Julia-AI-Assistant / Market Brain 相关仓库。**

本宪法目标只有一个：

> **任何时候，项目只能存在一个开发真相。**

任何规则、任务卡、Review 结论、历史分支、旧文档、自动化 Agent，都不得凌驾于本宪法。

---

## 受保护研究线例外

Mira 人格 / continuity 实验线与 RD1 开发 authority 严格隔离：

```text
mira/*
= PROTECTED RESEARCH LINE
= NEVER DELETE BY RD1 CLEANUP
= NO RD1 DEVELOPMENT AUTHORITY
= MUST NOT BE USED AS RD1 TASK BASE
= MUST NOT BE USED AS RD1 FALLBACK
= NOT COUNTED AS RD1 LONG_LIVED_WRITABLE_BRANCH
```

本例外仅用于保护研究资产，不赋予 `mira/*` 任何 RD1 canonical / recovery / production authority。

---

## 军规一：永远只有一条长期开发主线

每个仓库最多允许：

```text
LONG_LIVED_WRITABLE_BRANCH_COUNT = 1
```

除唯一主线外，任何开发分支都必须是短生命周期任务分支。

禁止创建或长期保留：

```text
second canonical branch
parallel recovery branch
parallel accepted branch
agent-specific long-lived branch
alternative integration branch
```

### 违反处置

```text
TASK = STOP
BRANCH = CLOSE
CANDIDATE = INVALID
```

---

## 军规二：任务分支只有两个结局——MERGE 或 DELETE

任何任务分支必须：

```text
create
→ implement
→ review
→ merge
→ delete
```

或者：

```text
create
→ reject
→ delete
```

不存在第三种状态。

禁止：

```text
accepted but unmerged
done but kept alive
maybe useful later
temporary branch becoming permanent
```

### DONE 的唯一合法定义

```text
CODE_COMPLETE
+
REVIEW_PASS
+
MERGED_TO_TRUNK
+
TRUNK_HEAD_VERIFIED
+
TASK_BRANCH_DELETED
```

缺任何一项：

```text
STATUS != DONE
```

---

## 军规三：Agent 永远无权自行选择开发基线

任何任务必须明确绑定：

```text
REPO
BASE_SHA
TARGET_BRANCH
TASK_ID
```

Agent 不得：

```text
search for a suitable branch
pick latest-looking branch
pick accepted-looking branch
pick PASS branch
pick recovery branch
pick branch by name
```

唯一合法起点：

```text
TASK_BASE_SHA == CURRENT_AUTHORIZED_TRUNK_SHA
```

不匹配立即 STOP。

---

## 军规四：分支名称没有任何权威

以下名字全部不能赋予 authority：

```text
main
release
production
accepted
canonical
recovery
final
fixed
golden
stable
```

工程事实只能来自：

```text
exact repository
exact SHA
exact ancestry
exact current trunk HEAD
```

禁止根据 branch 名称推断可信度。

---

## 军规五：ACCEPTED 不等于 MERGED

任何：

```text
PASS
APPROVED
ACCEPTED
TESTS PASSED
REVIEW COMPLETE
```

都只代表候选状态。

只有满足：

```text
candidate SHA
is ancestor of
current trunk HEAD
```

才算完成集成。

否则：

```text
CANDIDATE_ACCEPTED_NOT_INTEGRATED
```

不得进入下一任务。

---

## 军规六：禁止任何生产 fallback

生产路径必须遵守：

```text
required dependency unavailable
→ typed failure
→ fail closed
```

永久禁止：

```text
new path fails
→ old path

canonical provider unavailable
→ legacy provider

real execution fails
→ mock / fake / stub / synthetic success

new architecture unavailable
→ historical implementation
```

生产 fallback 数量：

```text
PRODUCTION_FALLBACK_COUNT = 0
```

发现一个，视为 P0。

---

## 军规七：历史代码只能是证据，不得成为第二真相

旧 commit、旧 branch、旧 PR 可以作为：

```text
REFERENCE
EVIDENCE
TEST SOURCE
POSTMORTEM SOURCE
```

不得自动成为：

```text
TASK BASE
CANONICAL BASE
RECOVERY AUTHORITY
FALLBACK SOURCE
```

历史节点需要保存时：

```text
TAG
```

而不是长期 branch。

---

## 军规八：Review 必须包含 Merge Closure

Code Review 不得只检查：

```text
diff
tests
architecture
scope
```

还必须检查：

```text
1. candidate exact SHA
2. target trunk exact SHA
3. merge completed
4. new trunk HEAD
5. candidate ancestor of trunk HEAD
6. task branch deleted
```

Review 没有完成 Merge Closure：

```text
REVIEW = INCOMPLETE
```

---

## 军规九：任何新任务必须从最新主线 HEAD 开始

禁止链式继承旧任务 branch：

```text
task A branch
→ task B based on A branch
→ task C based on B branch
```

正确方式：

```text
task A
→ merge trunk
→ delete

task B
→ branch from new trunk HEAD
→ merge trunk
→ delete

task C
→ branch from new trunk HEAD
```

每个任务都重新回到唯一主线。

---

## 军规十：任何 Agent 不得通过考古重建“当前真相”

新 Agent 启动后，不应阅读几十条历史 branch 来决定项目状态。

它只需要确认：

```text
AUTHORIZED_TRUNK
AUTHORIZED_HEAD_SHA
TASK_BASE_SHA
```

如果这些信息不能唯一确定：

```text
STOP
```

禁止 Agent：

```text
guess
infer
reconstruct authority from old chats
infer authority from old PASS
infer authority from PR comments
infer authority from branch history
```

项目当前真相必须在 1 分钟内机械确认。

---

# 一票否决事项

出现以下任何一种情况，任务立即终止：

```text
SECOND_LONG_LIVED_DEVELOPMENT_BRANCH
WRONG_BASE_SHA
UNMERGED_ACCEPTED_CANDIDATE
OLD_BRANCH_USED_AS_NEW_TASK_BASE
PRODUCTION_FALLBACK
SYNTHETIC_SUCCESS
BRANCH_NAME_USED_AS_AUTHORITY
NEXT_TASK_STARTED_BEFORE_PREVIOUS_MERGE_CLOSURE
REJECTED_BRANCH_LEFT_ACTIVE
AGENT_SELF_SELECTED_BASE
```

处置统一为：

```text
STOP
INVALIDATE CANDIDATE
CLOSE TASK BRANCH
RETURN TO SOLE TRUNK
RESTART FROM AUTHORIZED HEAD
```

---

# 仓库最终应长期保持的形态

正常状态：

```text
main
```

开发期间最多：

```text
main
├── task/ABC-123
├── task/ABC-124
└── task/ABC-125
```

任务结束后重新回到：

```text
main
```

不允许长期变成多条并行 RD1 development lineage。

`mira/*` 属于受保护研究线，不参与 RD1 development authority，也不计入上述 RD1 长期开发主线数量。

---

# Agent Task Card 第一条强制条款

任何 Agent / Codex / Claude / Mira / 自动化任务卡第一条必须写：

> **违反 `DEVELOPMENT_CONSTITUTION.md` 任一军规，立即 STOP，不得自行解释、绕过、降级、创建例外或继续实现。**

如任务卡与本宪法冲突：

```text
CONSTITUTION_WINS
TASK = STOP
OWNER_ADJUDICATION_REQUIRED = 1
```

---

# 永久原则

```text
ONE TRUNK
ONE CURRENT HEAD
ONE TASK BASE
NO FALLBACK
MERGE OR DELETE
```

任何工程流程如果让开发者或 Agent 再次面对“到底哪个分支才是真的”这个问题：

> **流程本身已经失败。**

项目不依赖 Agent 的记忆来保持正确。

项目必须依靠仓库结构本身，使错误选择变得不可能。
