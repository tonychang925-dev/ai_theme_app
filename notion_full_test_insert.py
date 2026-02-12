from notion_client import Client
import os
from datetime import datetime

NOTION_TOKEN = os.getenv("NOTION_TOKEN")

notion = Client(auth=NOTION_TOKEN)

DS = {
    "milestones": "3047bab0-ee1d-803a-a252-000b9489ab7d",
    "tasks": "3047bab0-ee1d-8075-b0bc-000bc97a0222",
    "reports": "3047bab0-ee1d-80ac-8929-000b8127392b",
    "reviews": "3047bab0-ee1d-803d-8752-000bc0c523b1",
    "adr": "3047bab0-ee1d-80a7-91f0-000b3697fa71",
}

print("🚀 开始插入模拟数据...\n")

# ------------------------------------
# 1️⃣ 创建 Milestone
# ------------------------------------

milestone = notion.pages.create(
    parent={"data_source_id": DS["milestones"]},
    properties={
        "Name": {
            "title": [{"text": {"content": "TEST - Phase2 验证链路"}}]
        },
        "Phase": {
            "select": {"name": "phase 2"}
        },
        "Status": {
            "select": {"name": "In progress"}
        },
        "Start": {
            "date": {"start": datetime.today().strftime("%Y-%m-%d")}
        },
        "Progress": {
            "number": 10
        },
        "Summary": {
            "rich_text": [{"text": {"content": "用于验证Notion自动同步流程"}}]
        },
        "Acceptance Gate": {
            "select": {"name": "Pending"}
        }
    }
)

milestone_id = milestone["id"]
print("✅ Milestone 创建成功")

# ------------------------------------
# 2️⃣ 创建 Task
# ------------------------------------

task = notion.pages.create(
    parent={"data_source_id": DS["tasks"]},
    properties={
        "Name": {
            "title": [{"text": {"content": "TEST - 构建语义工作副本"}}]
        },
        "Status": {
            "select": {"name": "Todo"}
        },
        "Priority": {
            "select": {"name": "P1"}
        },
        "Milestone": {
            "relation": [{"id": milestone_id}]
        }
    }
)

task_id = task["id"]
print("✅ Task 创建成功")

# ------------------------------------
# 3️⃣ 创建 Phase Report
# ------------------------------------

report = notion.pages.create(
    parent={"data_source_id": DS["reports"]},
    properties={
        "Name": {
            "title": [{"text": {"content": "TEST - Phase2 中期报告"}}]
        },
        "Status": {
            "select": {"name": "Draft"}
        },
        "Scope": {
            "rich_text": [{"text": {"content": "完成语义工作副本 + 规则引擎重构"}}]
        },
        "Milestone": {
            "relation": [{"id": milestone_id}]
        }
    }
)

report_id = report["id"]
print("✅ Phase Report 创建成功")

# ------------------------------------
# 4️⃣ 创建 Review
# ------------------------------------

review = notion.pages.create(
    parent={"data_source_id": DS["reviews"]},
    properties={
        "Name": {
            "title": [{"text": {"content": "TEST - 架构评审"}}]
        },
        "Type": {
            "select": {"name": "Architecture"}
        },
        "Status": {
            "select": {"name": "open"}
        },
        "Milestone": {
            "relation": [{"id": milestone_id}]
        },
        "Report": {
            "relation": [{"id": report_id}]
        }
    }
)

print("✅ Review 创建成功")

# ------------------------------------
# 5️⃣ 创建 ADR
# ------------------------------------

adr = notion.pages.create(
    parent={"data_source_id": DS["adr"]},
    properties={
        "Name": {
            "title": [{"text": {"content": "TEST - 采用双工作副本架构"}}]
        },
        "Status": {
            "select": {"name": "Proposed"}
        },
        "Context": {
            "rich_text": [{"text": {"content": "需要解决规则引擎与语义更新冲突"}}]
        },
        "Decision": {
            "rich_text": [{"text": {"content": "采用SemanticWorkingCopy + RuleWorkingCopy分离模型"}}]
        },
        "Milestone": {
            "relation": [{"id": milestone_id}]
        }
    }
)

print("✅ ADR 创建成功")

print("\n🎉 全部模拟数据插入完成！\n")
