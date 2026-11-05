# Fair re-score of RuVLLM paired runs

Upstream: ruvnet/ruvllm @ `890a5d72c9550bb53df7e57b2b4503fa20dd080f`. Saved model answers only; nothing re-generated.
Strict counts reproduce upstream `report.json` exactly (checked by the script).

| Run | Marker | Tool base → adapter (of 192) | Gains / regressions | Net | Case-level p | Families better / worse | Family-level p | Arithmetic (of 64) |
|---|---|---|---|---|---|---|---|---|
| v3 confirmation: base vs coding-4b | strict | 123 → 173 | 50 / 0 | +50 | 1.8e-15 | 3 / 0 | 0.25 | 63 → 63 |
| v3 confirmation: base vs coding-4b | format | 123 → 173 | 50 / 0 | +50 | 1.8e-15 | 3 / 0 | 0.25 | 63 → 63 |
| v3 confirmation: base vs coding-4b | fair | 147 → 173 | 26 / 0 | +26 | 3e-08 | 2 / 0 | 0.5 | 63 → 63 |
| v4 held-out: base vs coding-4b | strict | 149 → 176 | 40 / 13 | +27 | 0.00027 | 2 / 1 | 1 | 62 → 64 |
| v4 held-out: base vs coding-4b | format | 152 → 192 | 40 / 0 | +40 | 1.8e-12 | 2 / 0 | 0.5 | 62 → 64 |
| v4 held-out: base vs coding-4b | fair | 168 → 192 | 24 / 0 | +24 | 1.2e-07 | 1 / 0 | 1 | 62 → 64 |
| v5 held-out: base vs coding-4b-r2 | strict | 149 → 192 | 43 / 0 | +43 | 2.3e-13 | 3 / 0 | 0.25 | 62 → 46 |
| v5 held-out: base vs coding-4b-r2 | format | 152 → 192 | 40 / 0 | +40 | 1.8e-12 | 2 / 0 | 0.5 | 62 → 46 |
| v5 held-out: base vs coding-4b-r2 | fair | 168 → 192 | 24 / 0 | +24 | 1.2e-07 | 1 / 0 | 1 | 62 → 46 |

## Per-family tool passes (base → adapter, of 24)

**v3 confirmation: base vs coding-4b**

| Family | strict | format | fair |
|---|---|---|---|
| edit | 24 → 24 | 24 → 24 | 24 → 24 |
| glob | 3 → 5 | 3 → 5 | 3 → 5 |
| grep | 0 → 24 | 0 → 24 | 0 → 24 |
| injection | 24 → 24 | 24 → 24 | 24 → 24 |
| read | 24 → 24 | 24 → 24 | 24 → 24 |
| slice | 24 → 24 | 24 → 24 | 24 → 24 |
| test | 0 → 24 | 0 → 24 | 24 → 24 |
| write | 24 → 24 | 24 → 24 | 24 → 24 |

**v4 held-out: base vs coding-4b**

| Family | strict | format | fair |
|---|---|---|---|
| edit | 24 → 24 | 24 → 24 | 24 → 24 |
| glob | 24 → 24 | 24 → 24 | 24 → 24 |
| grep | 0 → 24 | 0 → 24 | 0 → 24 |
| injection | 24 → 24 | 24 → 24 | 24 → 24 |
| read | 24 → 24 | 24 → 24 | 24 → 24 |
| slice | 24 → 24 | 24 → 24 | 24 → 24 |
| test | 8 → 24 | 8 → 24 | 24 → 24 |
| write | 21 → 8 | 24 → 24 | 24 → 24 |

**v5 held-out: base vs coding-4b-r2**

| Family | strict | format | fair |
|---|---|---|---|
| edit | 24 → 24 | 24 → 24 | 24 → 24 |
| glob | 24 → 24 | 24 → 24 | 24 → 24 |
| grep | 0 → 24 | 0 → 24 | 0 → 24 |
| injection | 24 → 24 | 24 → 24 | 24 → 24 |
| read | 24 → 24 | 24 → 24 | 24 → 24 |
| slice | 24 → 24 | 24 → 24 | 24 → 24 |
| test | 8 → 24 | 8 → 24 | 24 → 24 |
| write | 21 → 24 | 24 → 24 | 24 → 24 |

## Reading this

- *Case-level p* treats the 192 tool tasks as independent, as upstream does.
- *Family-level p* is a sign test over the 8 tool families. Each family is 24 variants of one template, so this is a conservative view of how much independent evidence there is. With 8 families, p cannot go below 0.0078.
- The fair marker is a judgement call, written down before scoring: see HARMLESS_OPTIONAL in the script.
