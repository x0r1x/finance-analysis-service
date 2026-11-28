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

### Per-book top-1 (`summary.top1_by_book`)

Derived from the same measured run (aggregate interest **3/6** = Packt **3/3** bound + RVI **0/3** ambiguous under lexical-only mapping). Future CLI runs emit this block directly.

| Book (`id`) | `cfads` | `debt_service` | `interest` |
|---|---|---|---|
| packt | **1.0** (1/1) | **1.0** (1/1) | **1.0** (3/3) |
| rvi | **1.0** (1/1) | **1.0** (1/1) | **0.0** (0/3) |

Private books (Ashan, …) appear here only when loaded via `eval/local/labels/` (not committed).

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

## Separate baseline at `91f4f015`

This section records a baseline. It is not a quality comparison with the earlier measurement. Matching numbers below do not show that PR #122 left mapping quality unchanged.

The two runs use the same Packt and RVI fixture books and leave the model servers off. A metric delta is valid only when every pin matches (see the pin rule at the top of this file). These pins do not match:

| Pin | Earlier measurement | This baseline |
|---|---|---|
| FAS git SHA | `01a5b5ac7deec35d4bb436e209d77ba291b059e3` | `91f4f0151c9b04030abb47b1ad5aa94ce6589d64` |
| command | `uv run fas eval mapping --prune cfads,debt_service` | `uv run fas eval mapping` |
| glossary | `g-0001:f4927b7adafa` | `g-0001:abb472e2c064` |

The glossary pin is `version_for(1, load_git_document())`. On `01a5b5ac` that seed is `g-0001:f4927b7adafa`. On `91f4f015` the glossary files differ, so the seed is `g-0001:abb472e2c064`. Repeating the earlier command on this SHA still publishes the new seed. The same pin and the same command cannot both be had here, so the activities are not comparable ([PROV-DM, Activity](https://www.w3.org/TR/prov-dm/#term-Activity)). The labeled set was not edited to fit either run ([Rules of Machine Learning](https://developers.google.com/machine-learning/guides/rules-of-ml)).

Auchan was not loaded. Machine-readable record, without workbooks: [eval/mapping/baseline.json](baseline.json).

`origin/main` for this baseline is `91f4f0151c9b04030abb47b1ad5aa94ce6589d64` (merge of PR #122, 28 Nov 2026, 16:45 Moscow, UTC+3). The parent of that merge is `068b24cd0145ba432e6adc6bece6a91e08b18d3b`.

Storage was not a live-stack volume. Redis 8.6.7 listened on `127.0.0.1:6391`, database 1, directory `/tmp/fas-eval-pr0-redis`. `FAS_DATA_DIR=/tmp/fas-eval-pr0-data` (local store; S3 off). The trace pointer is the DuckDB file in that directory. Builder identity: `FixtureBuilder` (`FAS_FIXTURE_DIR=tests/fixtures/builder`). Taxonomy `core-1`. Calibrator `none`. `FAS_VERSION=0.23.0`. `catalog_version` `e5e47aa50edf3a3e`.

### Observed values

A cell in “values match” only says the two observed cells are the same. “Experiments comparable” is no on every row.

| Metric | Earlier run observed | This run observed | Values match | Experiments comparable |
|---|---|---|---|---|
| books | 2 | 2 | yes | no |
| accepted binds | 7 | 7 | yes | no |
| top-1 `cfads` | 1.0 (2/2) | 1.0 (Packt 1/1, RVI 1/1) | yes | no |
| top-1 `debt_service` | 1.0 (2/2) | 1.0 (Packt 1/1, RVI 1/1) | yes | no |
| top-1 `interest` | 0.5 (3/6) | 0.5 (Packt 3/3, RVI 0/3) | yes | no |
| false binding rate (all / metric) | 0.0 / 0.0 | 0.0 / 0.0 | yes | no |
| NIL recall / critical | 1.0 / 1.0 | 1.0 / 1.0 | yes | no |
| NIL precision | 0.785714 | 0.785714 | yes | no |
| ECE / Brier | not_measured | null / null | no | no |
| `targets.passed` | false | false | yes | no |

### Fact-row counts on this baseline

Bound / ambiguous / unknown / not_applicable, observed on this run. The existing contract test still owns the locked counts. This baseline does not rewrite them, `golden_count`, or the golden suite.

| Book | `job_id` | This run |
|---|---|---|
| Packt | `2eca70a9acd0c7b1812adcb2e1a4aacc84092f52726d001a93b9564950e5dd5e` | 11/2/80/4 |
| RVI | `2f180b3eec3b8557908beafa659af75dd7c2e93dab02b176f3cab1d625ee7bac` | 11/6/212/9 |

### `derive_key`

Both books share one key: `state_seq` is 0, the version inputs match, and the key does not include `job_id`.

| | `derive_key` | `fas_derive_version` |
|---|---|---|
| Parent tree `068b24cd`, same other inputs | `68f1c9d7b83b8621` | `cfd5ac68a8a7690015619589e6af5f4318c96393e6da79ba8516346ce50852a6` |
| This checkout | `8b310e3be2d3a418` | `03e31052da6cb264dcf60eec2979f4a5a8d5438ff7db5944a7c8d94f3a3b9d60` |

Other inputs, same on both sides: glossary `g-0001:abb472e2c064`, taxonomy `core-1`, calibrator `none`, empty model names, profile `p-0`, model types `dd84154239228158`, `model_type_seq` 0, sheet roles `14de2fdd4ed0c548`.

`baseline.json` stores a sha256 for every fingerprint member at the parent commit. `test_fingerprint_delta_is_the_changed_members` hashes the current members and keeps the paths whose digests differ. That set is `application/mapping_pipeline.py`, `application/project.py`, and `domain/semantics.py`. `application/learning.py` and the Builder load are not members of the fingerprint, so they are not in that set. `PACKAGE_SOURCES` was not edited to recover the parent key.

`catalog_version` stays `e5e47aa50edf3a3e`. `catalog_version_for` hashes indicator records. This baseline does not change those records.
