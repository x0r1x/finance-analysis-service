# Local-only mapping labels

Client books (e.g. the private CF workbook under builder `resources/corpus/`) are **not** committed.

Pattern (same idea as K3 / escrow):

1. Set `FAS_EVAL_DIR` to a local overlay that contains both committed `eval/labels/*.json` and extra local label files, **or** keep a private `eval/local/labels/*.json` and point `FAS_EVAL_DIR=eval/local` only for private runs.
2. Keep client-identifying paths/names out of git. Sibling `*.local.yaml` is gitignored.
3. Do not commit private xlsx/xls.

This directory’s label JSON (if any) is local scratch; see `.gitignore` for `eval/local/labels/`.
