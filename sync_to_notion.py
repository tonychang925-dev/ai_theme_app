from notion_client import Client
import os

NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATA_SOURCE_ID = "3047bab0-ee1d-803a-a252-000b9489ab7d"

notion = Client(auth=NOTION_TOKEN)

def create_milestone():
    notion.pages.create(
        parent={"data_source_id": DATA_SOURCE_ID},
        properties={
            "Name": {
                "title": [
                    {"text": {"content": "Phase2 - 语义演化引擎落地"}}
                ]
            },
            "Phase": {
                "select": {"name": "phase 2"}
            },
            "Status": {
                "select": {"name": "In progress"}
            },
            "Start": {
                "date": {"start": "2026-02-12"}
            },
            "due": {   # ⚠️ 小写
                "date": {"start": "2026-03-01"}
            },
            "Progress": {   # ⚠️ 没有 %
                "number": 20
            },
            "Summary": {
                "rich_text": [
                    {"text": {"content": "实现SemanticWorkingCopy与规则引擎双轨结构"}}
                ]
            },
            "Acceptance Gate": {
                "select": {"name": "Pending"}
            }
        }
    )

create_milestone()
