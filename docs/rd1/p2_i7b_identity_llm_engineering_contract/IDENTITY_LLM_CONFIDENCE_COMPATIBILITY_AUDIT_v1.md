# Identity LLM Confidence Compatibility Audit v1

## Selected Representation

```text
DOMAIN_TYPE
= decimal.Decimal

DOMAIN_SCALE
= ratio 0.0000..1.0000

PERSISTENT_REGISTRY_TYPE
= integer basis points 0..10000

ONE_BASIS_POINT
= 0.0001
```

Example:

```text
provider confidence 0.85
→ domain Decimal("0.8500")
→ registry integer 8500
→ read-back Decimal("0.8500")
→ public review confidence 0.8500
```

This eliminates the known lossy path:

```text
Decimal("0.85")
→ int(Decimal("0.85"))
→ 0
```

## Current Producer and Carrier

Current canonical code:

- parses provider confidence into `Decimal`;
- stores it on `IdentityLLMReviewVerdict.confidence`;
- passes that `Decimal` to `BuildIdentityJob`.

No semantic scale change occurs before the domain object.

## Current Lossy Points

### Registry row

Current code performs:

```python
int(llm_verdict.confidence)
```

This truncates every ratio below `1` to zero. The compiled contract removes this cast.

### Database writer

Current `PostgresDatabaseManager` performs another integer conversion:

```python
int(row.get("llm_confidence") or 0)
```

The historical registry DDL declares `llm_confidence INTEGER`. The compiled representation therefore converts a four-decimal domain ratio losslessly to integer basis points before this boundary.

### Review queue

Current queue evidence stores:

```python
str(row.get("llm_confidence") or "0")
```

The compiled queue evidence stores the canonical four-decimal ratio string, while queue priority stores basis points. This preserves both ordering magnitude and exact read-back.

### Intel consumer

Current `intel_new_chain_adapter` converts the persisted value directly:

```python
float(row.get("llm_confidence") or 0)
```

Once registry storage is basis points, this adapter must divide by `10000` before public float conversion. Until implementation, no persisted value may be interpreted as a ratio.

## Exact Conversion Rules

### Provider to domain

1. Parse numeric token as `Decimal`.
2. Require no exponent syntax.
3. Require at most four fractional digits.
4. Require `0 <= value <= 1`.
5. Do not round.
6. Quantize presentation to four places only after validation.

### Domain to registry basis points

```text
basis_points = confidence * 10000
```

The result must be an exact integer. Any fractional remainder is `CONTRACT_INVALID`; rounding is forbidden.

### Registry to domain

```text
confidence = Decimal(basis_points) / Decimal(10000)
```

Canonical output is four decimal places.

### Domain to queue

```text
evidence["llm_confidence"]
= format(confidence, ".4f")

priority_score
= basis_points
```

### Domain to public/intel consumer

```text
confidence
= float(basis_points / 10000)
```

The public semantic remains a judgment-confidence ratio, not a composite/rule score or final identity probability.

## Persistence Compatibility

The selected basis-point integer fits the existing documented `INTEGER` column with range `0..10000` and requires no DB schema migration. This task authorizes no migration.

## Roundtrip Test Requirements

A later focused implementation must test at minimum:

| Input | Stored | Read-back |
|---|---:|---:|
| `0` | `0` | `0.0000` |
| `0.0001` | `1` | `0.0001` |
| `0.85` | `8500` | `0.8500` |
| `1` | `10000` | `1.0000` |

It must reject:

- more than four fractional digits;
- negative or greater-than-one values;
- numeric strings;
- exponent notation;
- `NaN` or infinity;
- non-exact basis-point conversion.

