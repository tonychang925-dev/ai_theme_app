# CR-CONSTITUTION-01 — NO CRITICAL FALLBACK (NCF-1)

## Rule

Critical Market and database dependencies must fail closed with typed non-success or startup failure. Unavailable PostgreSQL, canonical Market composition, D1, provider authority, evidence, authentication, or provenance must never fall back to memory, mock, fixture, legacy storage, alternate authority, synthetic success, ambient resolution, or test mode.

## Severity and enforcement

- `P0`: reject and block release.
- `P1`: reject.
- `P2`: review required.
- `P3`: safe test-only fixture with no production reachability.

New `P0/P1` findings fail. Existing debt is accepted only by exact rule/file/fingerprint in `ncf-baseline.json`; modification or expansion fails. Reports preserve `EXISTING_DEBT`, `NEW_VIOLATIONS`, and `RESOLVED_DEBT`. New baseline entries require `EXPLICIT_TONY_AUTHORIZATION`.

## Preselection is not fallback

Continuing a previously selected plan `[A,B,C]` with `B` after `A` fails is allowed. Selecting a new `D` after `A` fails is fallback and is prohibited for critical authority.

## Workflow

```sh
./hooks/install-hooks.sh
python3 tools/no_critical_fallback_gate.py --repo ai_theme_app --baseline ncf-baseline.json
```

The bootstrap baseline records 564 accepted findings: 155 `P1` and 409 `P2`. Updating it requires the authorization token and is reviewable as a change to `ncf-baseline.json`:

```sh
python3 tools/no_critical_fallback_gate.py --repo ai_theme_app --baseline ncf-baseline.json \
  --update-baseline \
  --authorization EXPLICIT_TONY_GO_NCF_A5_LOCAL_CODEX_CI_GITHUB_ENFORCEMENT
```

Commit checks staged production files; push and CI check the repository plus negative composition tests. Local hooks are convenience only; CI is the authoritative local-side execution and GitHub protection is the merge boundary.
