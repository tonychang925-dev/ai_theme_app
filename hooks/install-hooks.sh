#!/bin/sh
set -eu

ROOT=$(git rev-parse --show-toplevel)
for hook in pre-commit pre-push; do
  destination="$ROOT/.git/hooks/$hook"
  if [ "${FORCE:-0}" != "1" ] && [ -e "$destination" ] && [ "${hook}.sample" != "$(basename "$destination")" ] && ! cmp -s "$ROOT/hooks/$hook" "$destination"; then
    echo "Refusing to replace existing $hook hook: $destination" >&2
    echo "Set FORCE=1 only after reviewing and preserving that hook." >&2
    exit 1
  fi
done
cp "$ROOT/hooks/pre-commit" "$ROOT/.git/hooks/pre-commit"
cp "$ROOT/hooks/pre-push" "$ROOT/.git/hooks/pre-push"
chmod +x "$ROOT/.git/hooks/pre-commit" "$ROOT/.git/hooks/pre-push"
