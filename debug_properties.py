from notion_client import Client
import os

NOTION_TOKEN = os.getenv("NOTION_TOKEN")

notion = Client(auth=NOTION_TOKEN)

DATA_SOURCES = {
    "ADR": "3047bab0-ee1d-80a7-91f0-000b3697fa71",
    "Phase Reports": "3047bab0-ee1d-80ac-8929-000b8127392b",
    "Reviews": "3047bab0-ee1d-803d-8752-000bc0c523b1",
    "Tasks": "3047bab0-ee1d-8075-b0bc-000bc97a0222",
    "Milestones": "3047bab0-ee1d-803a-a252-000b9489ab7d"
}

print("\n==============================")
print("🔍 读取所有 Data Source 字段")
print("==============================\n")

for name, ds_id in DATA_SOURCES.items():
    print(f"\n\n===== {name} =====")
    print("Data Source ID:", ds_id)
    print("----------------------------------------")

    ds = notion.data_sources.retrieve(ds_id)

    for prop_name, prop in ds["properties"].items():
        print("字段名:", prop_name)
        print("  类型:", prop["type"])
        print("  Property ID:", prop["id"])

        if prop["type"] == "select":
            print("  选项:")
            for opt in prop["select"]["options"]:
                print("    -", opt["name"])

        if prop["type"] == "multi_select":
            print("  选项:")
            for opt in prop["multi_select"]["options"]:
                print("    -", opt["name"])

        if prop["type"] == "relation":
            print("  关联 Data Source ID:",
                  prop["relation"].get("data_source_id"))

        print("----------------------------------------")

print("\n\n✅ 所有字段读取完成\n")
