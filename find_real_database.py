from notion_client import Client
import os

token = os.getenv("NOTION_TOKEN")

if not token:
    raise Exception("NOTION_TOKEN 环境变量没有设置")

notion = Client(auth=token)

print("🔍 搜索所有数据源...\n")

response = notion.search(
    filter={
        "property": "object",
        "value": "data_source"
    }
)

if not response["results"]:
    print("❌ 没有找到任何 data_source。说明 Integration 没连接到数据库。")
else:
    for ds in response["results"]:
        title = ds["title"][0]["plain_text"] if ds["title"] else "无标题"
        print("数据源名称:", title)
        print("Data Source ID:", ds["id"])
        print("-" * 40)
