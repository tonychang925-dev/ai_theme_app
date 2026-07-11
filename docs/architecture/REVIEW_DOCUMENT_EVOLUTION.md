# ReviewDocument Evolution Policy

> 版本：v0.1  
> 日期：2026-07-11  
> 状态：Active  
> 目的：定义 ReviewDocument schema 的演进规则，防止字段漂移和历史复盘被新版本重新解释。

---

## 1. Version Fields

ReviewDocument metadata 必须包含：

```json
{
  "document_schema_version": "review_document_v1",
  "review_document_schema_version": "1.0",
  "snapshot_schema_version": "4.5.7",
  "assembler_version": "assembler_v1.0",
  "snapshot_hash": "sha256:...",
  "final_document_hash": "sha256:..."
}
```

---

## 2. Minor Change

允许：

1. 新增 optional field。
2. 新增 `field_provenance` 条目。
3. 新增非阻断 warning。
4. 新增只读 debug metadata。

要求：

1. 不改变既有字段语义。
2. 不改变 required field。
3. 不改变 Golden Fixture 的既有断言。
4. `review_document_schema_version` 可从 `1.0` 升到 `1.1`。

---

## 3. Major Change

以下情况必须升级 major version：

1. 删除字段。
2. required field 变化。
3. 字段语义变化。
4. section 结构变化。
5. `ReviewDocumentAssembler` 输出逻辑变化会影响历史复现。
6. quality gate 阻断规则变化。

要求：

1. `document_schema_version` 升级，例如 `review_document_v2`。
2. `assembler_version` 升级，例如 `assembler_v2.0`。
3. 新增 migration note。
4. 新增或更新 Golden Fixture。
5. 保留旧版本复现能力。

---

## 4. Prohibited Changes

禁止：

1. 偷偷增加 required field。
2. 复用旧字段名但改变语义。
3. 不更新 version 就改变 output。
4. 让新 assembler 重新解释旧 approved document。
5. 在 ReviewDocument 之外新增第二套正式展示协议。

---

## 5. Historical Reproducibility

历史复盘必须按 approved manifest 复现：

```text
snapshot_hash
  + document_schema_version
  + assembler_version
  -> ReviewDocument
  -> final_document_hash
```

若 hash 不一致，说明历史复现失败，必须阻断回测或学习任务。

