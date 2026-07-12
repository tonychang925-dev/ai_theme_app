# Architecture Guard Policy

> Phase 4.5.7 — AI Agent Development Constraints

## Rule 1: Data Field Lifecycle

Every new data field MUST follow:

```
Snapshot Producer  →  ContextFactory  →  ReviewDocumentAssembler  →  UI
```

**Forbidden shortcuts**:
- API response assembly (no `response["field"] = x`)
- Frontend calculation (no `const value = a / b * 100`)
- Assembler inference (no `if score > 30: level = "HIGH"`)
- Static JSON fallback (no `if not data: data = json.load(file)`)

## Rule 2: AI Modification Protocol

Before modifying any file, the AI agent MUST identify which layer it's touching:

| Layer | Allowed operations | Forbidden |
|---|---|---|
| Producer | field rename, copy, type cast | classify, filter, infer, calculate, fallback |
| ContextFactory | whitelist extraction | business logic, field derivation |
| Assembler | field mapping, format conversion | fallback, inference, default fabrication |
| UI Component | display reviewDocument fields | fetch legacy APIs, consume raw props |

## Rule 3: Exception Protocol

Any code that violates `architecture_rules.yaml` MUST register an exception in `architecture_exceptions.yaml` with:
- `id`: unique identifier
- `owner`: responsible person
- `expire`: hard deadline (max 14 days)
- `replacement`: plan for removing the exception

Expired exceptions → CI blocks the build.

## Rule 4: ReviewDocument is the Single Growth Target

New capability → `ReviewDocument` schema.  Never add to:
- FormalReviewProjectionCompiler
- legacy recap_doc
- static emotion/chart JSON
- DailyReview secondary assembly

## Rule 5: Quality over Display

Missing data → `quality=MISSING` or `BLOCKED`.  Never:
- Fabricate a value to make the page look complete
- Fall back to an alternate data source
- Drop rows to clean up the display
- Infer from unrelated fields
