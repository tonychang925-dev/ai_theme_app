from notion_client import Client
import os
from datetime import datetime

class NotionSyncManager:

    def __init__(self):
        self.notion = Client(auth=os.getenv("NOTION_TOKEN"))

        self.DS = {
            "milestones": "3047bab0-ee1d-803a-a252-000b9489ab7d",
            "tasks": "3047bab0-ee1d-8075-b0bc-000bc97a0222",
            "reports": "3047bab0-ee1d-80ac-8929-000b8127392b",
            "reviews": "3047bab0-ee1d-803d-8752-000bc0c523b1",
            "adr": "3047bab0-ee1d-80a7-91f0-000b3697fa71",
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

    def create_task(self, milestone_id, name, priority="P1"):
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
