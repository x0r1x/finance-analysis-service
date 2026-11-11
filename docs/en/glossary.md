# Glossary

[Русский](../ru/glossary.md)

The glossary is FAS data. The git package is `configs/concepts/`, `configs/glossary/`, and `configs/metrics/`. A release is an immutable copy of that document in the object store. Book loads record the release id they were built with.

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

## Profiles

A profile is a per-book overlay of labels and a few book settings.

- `GET /v1/profiles`
- `GET /v1/profiles/{profile}`
- `PUT /v1/profiles/{profile}`
