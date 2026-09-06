# Codex Repository Instructions

Before editing or reviewing critical production code, load `.agents/skills/NO_CRITICAL_FALLBACK_REVIEW/SKILL.md` and follow it. Run `tools/no_critical_fallback_gate.py` before preparing a commit when critical production files change. New `P0/P1` NCF findings require `DECISION = REJECT` and `COMMIT_ALLOWED = NO`.
