# Glossary

[Русский](../ru/glossary.md)

The glossary is FAS data. The git package is `configs/concepts/`, `configs/glossary/`, and `configs/metrics/`. A release is an immutable copy of that document in the object store. Book loads record the release id they were built with.

`borrowings_lt`, `borrowings_st` and `lease_liability` are the stock lines behind `total_debt`. `total_debt` itself is a metric in `configs/metrics/coverage.yaml`, not a row concept. The labels «Заемные средства» and «Займы и кредиты» are ambiguous and resolve from the line code, the section heading, or a debt-model sheet.

`GLOSSARY_AUTO_PROMOTE` defaults to off. A label learned from books does not become the active release by itself. `uv run fas glossary shadow <version>` builds the shadow report for a candidate. The thresholds and the canary gate are in [design-v0.23.md](../design-v0.23.md) §5.9, not on this page.

Labeled books and the `fas eval mapping` command are described in [eval/README.md](../../eval/README.md).

## Read and write

`GET /v1/glossary` returns the head and an `ETag` of `h-{seq}`. Without a published head it returns `404` and does not write.

`POST /v1/glossary/bootstrap` publishes the git package as release 1 when no head exists. A repeat call returns the current head. When `FAS_ADMIN_TOKEN` is set, this route requires `X-Admin-Token`. The CLI equivalent is `uv run fas glossary bootstrap`. Cron jobs (`glossary_mine`, `cluster_unmapped`) and `fas eval` / `fas learn` require a head already; they do not publish.

These reads only read. Without a head they return `404` and never call `_publish_git`:

- `GET /v1/glossary`
- `GET /v1/glossary/releases`
- `GET /v1/glossary/releases/{version}`
- `GET /v1/glossary/content`
- `GET /v1/glossary/concepts`
- `GET /v1/glossary/diff`
- `GET /v1/glossary/events`

These do not publish either:

- `GET /v1/glossary/labels?q=`
- `GET /v1/glossary/impact` — **deprecated**; always `501 not_implemented`. The design contract is `GET /v1/glossary/releases/{version}/impact` (not implemented yet). Do not treat `{"books": []}` as a real index.
- `GET /v1/glossary/stats?from=&to=&profile_id=`
- `GET /v1/glossary/proposals` and `GET /v1/glossary/proposals/{proposal_id}`
- `POST /v1/glossary:resolve`

Writes:

- `POST /v1/glossary/bootstrap` — first release from git (idempotent).
- `POST /v1/glossary/releases` — create a release from `ops`, or replace the document when `mode` is `replace`. Requires a head (`404` until bootstrap).
- `POST /v1/glossary/transitions` — move a release to another status. The request enqueues a `glossary.validate` operation on `fas:glossary`; the worker runs the shadow check and the write. A successful transition starts a book remap.
- `POST /v1/glossary:rollback` — activate the previous release and start a remap.
- `POST /v1/glossary/proposals` and `POST /v1/glossary/proposals:decide` — open a proposal, or accept and reject a batch.

When `FAS_ADMIN_TOKEN` is set, bootstrap, releases, transitions, rollback, proposal decisions, and `PUT /v1/profiles/{profile}` require the header `X-Admin-Token` (checked before idempotency replay). When it is empty, those routes do not check a token. Production should set `FAS_REQUIRE_ADMIN_TOKEN=true` so a missing token fails startup (fail-closed); see [settings — auth perimeter](settings.md#auth-perimeter-prod). `X-User-Id` is still not authentication.

## Resolve

`POST /v1/glossary:resolve` maps one label to a concept. The body is an object. Send `label` or `text`, or send `path_text` and the last segment after ` › ` is the label. Sending both `label` and `path_text` is `400`. Optional fields are `unit`, `profile_id`, and `version`.

The call does not write. A `version` that is not in the store is `404` and does not publish the git package. With no published head, the answer comes from the git document and `state` is null.

A lexical hit that fails the unit check stays in `candidates` with `structure_pass: false` and `match` null. The model is not asked. A label with no lexical hit is ranked only when an embed or rerank server is configured, and that rank does not spend the per-book choice-model budget.

## Concept relations

The type registry is `finance_analysis.domain.relations`. Edges still live on the concept in `configs/concepts/`. There is no separate relation graph. `relation_targets` reads only stored edges: `dscr` has an empty `related_to` list. `GlossaryPackage.semantic_targets` reads the meaning and does not change the document. For a symmetric type it adds incoming edges, so `dscr` is semantically related to `cfads`. For the `broader_than` / `narrower_than` pair, asking for the inverse type sees the edge stored on the other side. Incoming sources are ordered by id, with no duplicates. `energy_tariff` and `forecast_energy_tariff` remain two explicit edges. `transitive` does not build a closure: walking ancestors or descendants will be a separate API, not `relation_targets`.

A semantic edge does not substitute one concept for another and does not sum its targets into a metric. Calculation asks the registry. No type currently grants substitution or aggregation. Reconciliation is only `composed_of`: that list matches `configs/identities/` and feeds the `lf.identity` vote. The parts are not summed into a metric input. `related_to` is not reconciliation, substitution, or aggregation.

`calculated_from` is a formula dependency, not a part list and not a license to compute from the edge. `derived_from` is semantic origin, without arithmetic. Both are active in the schema and empty in the catalog. `equivalent_to`, `supersedes`, and `replaced_by` are inactive: a package that uses them does not load. Accrued `interest` and paid `interest_paid` are not equivalent.

| Type | Status | Direction | Transitive | Inverse | Inverse required | Cycles | Substitution | Aggregation | Reconciliation | Ends |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `composed_of` | active | directed | no | none | no | no | no | no | yes | measure → measure, same dimension |
| `calculated_from` | active | directed | no | none | no | no | no | no | no | concept → concept |
| `derived_from` | active | directed | no | none | no | no | no | no | no | concept → concept |
| `broader_than` | active | directed | yes | `narrower_than` | no | no | no | no | no | concept → concept |
| `narrower_than` | active | directed | yes | `broader_than` | no | no | no | no | no | concept → concept |
| `related_to` | active | symmetric | no | itself | no | yes | no | no | no | concept → concept |
| `equivalent_to` | reserved | symmetric | yes | itself | no | yes | no | no | no | concept → concept |
| `supersedes` | reserved | directed | no | `replaced_by` | no | no | no | no | no | concept → concept |
| `replaced_by` | reserved | directed | no | `supersedes` | no | no | no | no | no | concept → concept |
| `contradicts` | active | symmetric | no | itself | no | yes | no | no | no | concept → concept |
| `requires` | active | directed | no | none | no | no | no | no | no | concept → concept |

Transitivity in the table is a property of the type. Loading does not build a closure. `broader_than`, `narrower_than`, and the published `broader` field stay one parent-to-child graph; a cycle there rejects the package. An unknown type, an inactive type, a role or dimension the type does not allow, an edge to a missing concept, a forbidden cycle, and a type paired with its inverse on the same ordered pair fail the load. The messages are in Russian.

## Profiles

A profile is a per-book overlay of labels and a few book settings.

- `GET /v1/profiles`
- `GET /v1/profiles/{profile}`
- `PUT /v1/profiles/{profile}`
