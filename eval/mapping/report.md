# Mapping eval report (Phase 2 slice)

**Scope:** measured on the **labeled set only** (`eval/labels/packt.json`, `eval/labels/rvi.json`) — **2 books**, not the 20–30-book target. Phase 2b gates remain **assumptions** until the corpus grows.

**Metric deltas without the pin set below are invalid** (not comparable across runs).

## Reproducibility pins

| Pin | Value |
|---|---|
| labels `schema_version` | `1` (`eval/labels/{packt,rvi}.json`) |
| glossary version | `g-0001:f4927b7adafa` (active at run; seed = `load_git_document()` / `version_for(1, …)`) |
| taxonomy version | `core-1` |
| builder identity | `FixtureBuilder` (`FAS_FIXTURE_DIR=tests/fixtures/builder`; Packt/RVI golden dumps) |
| FAS git SHA | `01a5b5ac7deec35d4bb436e209d77ba291b059e3` (checkout used for this measured run; rebased on current `main`) |
| mapping / FAS version | `FAS_VERSION=0.23.0` |
| book source + `job_id` | Packt: builder `resources/corpus/packt-project-finance.xlsx` → fixture `job_id` `2eca70a9acd0c7b1812adcb2e1a4aacc84092f52726d001a93b9564950e5dd5e`; RVI: builder `resources/corpus/rvi-project-finance.xlsx` → fixture `job_id` `2f180b3eec3b8557908beafa659af75dd7c2e93dab02b176f3cab1d625ee7bac` |
| exact cmdline | `uv run fas eval mapping --prune cfads,debt_service` |
| calibrator version | `none` (ECE/Brier **not_measured** — no calibrated confidences) |
| NIL metric contract | `NIL_STATUSES={unknown, ambiguous}` (see `eval/README.md`) |

**Environment (local Mac):**

- Redis 8.6.7 (`FAS_REDIS_URL=redis://127.0.0.1:6391/1`)
- Storage: `FAS_DATA_DIR=/tmp/fas-eval-data`
- `FAS_EVAL_DIR=$PWD/eval`
- Models: off (no `EMBED`/`RERANK`/`CLM` URLs) — lexical/glossary path only

**Corpus inventory**

| Book | Source | Labels |
|---|---|---|
| Packt | builder `resources/corpus/packt-project-finance.xlsx` + FAS fixture `packt` | commit-safe `eval/labels/packt.json` |
| RVI | builder `resources/corpus/rvi-project-finance.xlsx` + FAS fixture `rvi` | commit-safe `eval/labels/rvi.json` |
| Private CF workbook (Ашан) | builder `resources/corpus/` private xls(x) (not in lock) | **local-only** — not committed; see `eval/local/README.md` |

No additional non-private books were available locally toward the 20–30 target (`corpus.lock.json` only Packt + RVI fetchable; `three-statement` unavailable).

## Command

```bash
export FAS_REDIS_URL=redis://127.0.0.1:6391/1
export FAS_DATA_DIR=/tmp/fas-eval-data
export FAS_FIXTURE_DIR=$PWD/tests/fixtures/builder
export FAS_EVAL_DIR=$PWD/eval
# load once via FixtureBuilder perform_load for packt + rvi job_ids
uv run fas eval mapping --prune cfads,debt_service
```

## Measured summary (`fas eval mapping`)

| Metric | Value |
|---|---|
| books | 2 |
| accepted binds (labeled) | **7** |
| top-1 `cfads` | **1.0** (correct/total **2/2**) |
| top-1 `debt_service` | **1.0** (correct/total **2/2**) |
| top-1 `interest` | **0.5** (correct/total **3/6**) |
| false binding rate (all) | **0.0** |
| false binding rate (metric) | **0.0** |
| NIL recall | **1.0** |
| NIL recall (critical) | **1.0** |
| NIL precision | **0.785714** (ambiguous non-NIL rows now count as NIL predictions) |
| ECE | **not_measured** (null; calibrator `none`, no confidence scores) |
| Brier | **not_measured** (null) |

### Status histogram (labeled eval rows, n=21)

| Status | Count |
|---|---:|
| bound | 7 |
| unknown | 11 |
| ambiguous | 3 |
| not_applicable | 0 |
| ignored | 0 |

### Phase 2b assumption checks (on this slice)

| Check | Result |
|---|---|
| top-1 ≥ 0.9 on focus | **fail** (`interest` 0.5 — RVI interest rows stay `ambiguous`, not `bound`) |
| ECE < 0.05 | **not_measured** (null ECE; calibrator off — not a fail) |
| false binds (metric) ≤ 2% | **pass** (0.0) |
| NIL recall critical ≥ 0.9 | **pass** (1.0) |
| overall `targets.passed` | **false** |

### BLINKout (`--prune cfads,debt_service`)

| Concept | rows | leaked | nil_recall |
|---|---:|---:|---:|
| cfads | 2 | 0 | 1.0 |
| debt_service | 2 | 0 | 1.0 |

Pruned concept rows did not leak into a neighboring concept on this labeled set.

## Notes

- Labels prefer stable `by_path` / `critical_paths`; fixture `binding_key`s pinned under `labels` / `critical` for Packt/RVI primaries.
- NIL rows (fees, rates, equity residual) correctly land in `unknown`/`ambiguous`, not nearest-neighbor binds. `not_applicable`/`ignored` are out of NIL recall/precision by contract.
- Interest gap is real on RVI under lexical-only mapping; do not treat 0.5 as a closed gate.
- Private workbook files and client-identifying label paths were **not** committed.

Raw CLI JSON: captured locally during the run (not required in git).
