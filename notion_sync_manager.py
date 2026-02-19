from notion_client import Client
import os
from datetime import datetime
from pathlib import Path


def _load_env_file_if_needed() -> None:
    """
    在 NOTION_TOKEN 缺失时，尝试从项目根目录 .env/.env.local 加载。
    仅填充当前进程缺失的变量，不覆盖已有环境变量。
    """
    if os.getenv("NOTION_TOKEN"):
        return

    root = Path(__file__).resolve().parent
    candidates = [root / ".env", root / ".env.local", root / ".venv" / "bin" / "activate"]
    for env_path in candidates:
        if not env_path.exists():
            continue
        try:
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("'").strip('"')
                if key and key not in os.environ:
                    os.environ[key] = value
        except Exception:
            # 环境文件解析失败时保持静默，交由后续 token 校验给出统一错误。
            continue
        if os.getenv("NOTION_TOKEN"):
            return

class NotionSyncManager:

    def __init__(self):
        _load_env_file_if_needed()
        token = os.getenv("NOTION_TOKEN")
        if not token:
            raise ValueError(
                "NOTION_TOKEN 未配置。请通过环境变量导出，或在项目根 .env 中设置 NOTION_TOKEN。"
            )
        self.notion = Client(auth=token)

        self.DS = {
            "milestones": "3047bab0-ee1d-803a-a252-000b9489ab7d",
            "tasks": "3047bab0-ee1d-8075-b0bc-000bc97a0222",
            "reports": "3047bab0-ee1d-80ac-8929-000b8127392b",
            "reviews": "3047bab0-ee1d-803d-8752-000bc0c523b1",
            "adr": "3047bab0-ee1d-80a7-91f0-000b3697fa71",
        }

    def token_fingerprint(self) -> str:
        token = os.getenv("NOTION_TOKEN", "")
        if len(token) < 6:
            return "***"
        return f"{token[:4]}...{token[-4:]}"

    def verify_token(self) -> dict:
        """
        通过 users.me 预检 token 可用性。
        """
        try:
            me = self.notion.users.me()
            user_type = me.get("type", "unknown")
            name = me.get("name") or me.get("bot", {}).get("owner", {}).get("type", "unknown")
            return {
                "ok": True,
                "token_fingerprint": self.token_fingerprint(),
                "user_type": user_type,
                "name": name,
            }
        except Exception as e:
            return {
                "ok": False,
                "token_fingerprint": self.token_fingerprint(),
                "error": str(e),
            }

    # ----------------------------
    # Milestone
    # ----------------------------

    def create_milestone(self, name, phase, summary):
        return self.notion.pages.create(
            parent={"data_source_id": self.DS["milestones"]},
            properties={
                "Name": {
                    "title": [{"text": {"content": name}}]
                },
                "Phase": {
                    "select": {"name": phase}
                },
                "Status": {
                    "select": {"name": "In progress"}
                },
                "Start": {
                    "date": {"start": datetime.today().strftime("%Y-%m-%d")}
                },
                "Progress": {
                    "number": 0
                },
                "Summary": {
                    "rich_text": [{"text": {"content": summary}}]
                },
                "Acceptance Gate": {
                    "select": {"name": "Pending"}
                }
            }
        )

    def update_progress(self, page_id, progress):
        self.notion.pages.update(
            page_id=page_id,
            properties={
                "Progress": {"number": progress}
            }
        )

    # ----------------------------
    # Task
    # ----------------------------

    def create_task(self, milestone_id, name, priority="P1", estimate=None, dependencies=None, dod_checklist=None):
        # 创建任务的核心逻辑
        return self.notion.pages.create(
            parent={"data_source_id": self.DS["tasks"]},
            properties={
                "Name": {
                    "title": [{"text": {"content": name}}]
                },
                "Status": {
                    "select": {"name": "Todo"}
                },
                "Priority": {
                    "select": {"name": priority}
                },
                "Milestone": {
                    "relation": [{"id": milestone_id}]
                },
                "Estimate": {
                    "number": estimate  # 这里设定任务估算的工时（如果提供了）
                },
                "Dependencies": {
                    "relation": dependencies if dependencies else []  # 如果有依赖任务，传入，否则为空列表
                },
                "DoD Checklist": {
                    "multi_select": dod_checklist if dod_checklist else []  # 提供DoD checklist（如果有的话）
                }
            }
        )


    # ----------------------------
    # Phase Report
    # ----------------------------

    def create_phase_report(self, milestone_id, name, scope):
        return self.notion.pages.create(
            parent={"data_source_id": self.DS["reports"]},
            properties={
                "Name": {
                    "title": [{"text": {"content": name}}]
                },
                "Status": {
                    "select": {"name": "Draft"}
                },
                "Scope": {
                    "rich_text": [{"text": {"content": scope}}]
                },
                "Milestone": {
                    "relation": [{"id": milestone_id}]
                }
            }
        )

    # ----------------------------
    # Review
    # ----------------------------

    def create_review(self, milestone_id, name, review_type="Architecture"):
        return self.notion.pages.create(
            parent={"data_source_id": self.DS["reviews"]},
            properties={
                "Name": {
                    "title": [{"text": {"content": name}}]
                },
                "Type": {
                    "select": {"name": review_type}
                },
                "Status": {
                    "select": {"name": "open"}
                },
                "Milestone": {
                    "relation": [{"id": milestone_id}]
                }
            }
        )

    # ----------------------------
    # ADR
    # ----------------------------

    def create_adr(self, milestone_id, name, context, decision):
        return self.notion.pages.create(
            parent={"data_source_id": self.DS["adr"]},
            properties={
                "Name": {
                    "title": [{"text": {"content": name}}]
                },
                "Status": {
                    "select": {"name": "Proposed"}
                },
                "Context": {
                    "rich_text": [{"text": {"content": context}}]
                },
                "Decision": {
                    "rich_text": [{"text": {"content": decision}}]
                },
                "Milestone": {
                    "relation": [{"id": milestone_id}]
                }
            }
        )
