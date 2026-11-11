# Local-only mapping labels

Client / private books (e.g. the Ashan CF workbook under builder `resources/corpus/`) are **not** committed.

Pattern (same idea as K3 / escrow):

1. Keep commit-safe labels in `eval/labels/` (`packt`, `rvi`, …).
2. Drop private label JSON under `eval/local/labels/` (gitignored). With default `FAS_EVAL_DIR=eval`, `fas eval mapping` **merges** both directories; a local file with the same `job_id` overrides the committed one. Optional `id` (defaults to the filename stem) keys `summary.top1_by_book`.
3. Keep client-identifying paths/names out of git. Sibling `*.local.yaml` is gitignored.
4. Do not commit private xlsx/xls.

You can still point `FAS_EVAL_DIR` at a private overlay tree if you prefer an isolated run.
