# Project overview

[Русский](../ru/overview.md)

FAS is the analysis service behind a parsed cash-flow book. [finance-context-builder](https://github.com/x0r1x/finance-context-builder) owns the workbook: layout, cached values, formulas, and the formula graph. FAS owns concepts, row bindings, period phases, signs, units, audit rules, coverage ratios, and reports.

## Input and output

`POST /v1/books/{job_id}:load` reads that `job_id` from the builder HTTP API (`BUILDER_BASE_URL`). FAS stores the projection as Parquet under `books/{job_id}/{build_key}/` and keeps human decisions in a numbered journal.

A later read returns the book head, the mapping, findings from the last audit, and a report rendered from the stored result. A second `GET` of the same report does not recompute it.

## What FAS does not do

FAS does not parse Excel, does not recalculate formulas, and does not call a model on its own behalf. `GET /v1/capabilities` is a card for the client. The client may hand `tools[]` to its own LLM. FAS never does that call.

`capabilities.phase` is the shipped phase. The code returns `"4"`. Renderers are `json` and `md`.

## Spec

Behavior that this page does not spell out is in [design-v0.23.md](../design-v0.23.md), §0 and §1. Where that document and the code disagree, the code is what the service does.

The meta-layer target model and delivery phases are in [meta-layer.md](../meta-layer.md) and [meta-layer-roadmap.md](../meta-layer-roadmap.md) (Russian). The financial-fact provenance contract (phase 1) is [financial-fact-provenance.md](../financial-fact-provenance.md) (Russian). The public `SemanticModelVersion` (phase 2) is [semantic-model-version.md](../semantic-model-version.md) (Russian). The Financial Model Catalog (phase 3) is [financial-model-catalog.md](../financial-model-catalog.md) (Russian).
