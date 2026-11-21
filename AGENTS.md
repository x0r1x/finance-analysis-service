# Agent contract

Setup: Python 3.12 and `uv sync`, as in README.md. If uv is missing, `pip install -e ".[dev]"`, as in `.github/workflows/ci.yml`. Run the checks after install.

Before saying the work is done, run only the tests you wrote or changed, plus these checks. Each must exit 0. A truncated log is not green.

- `uv run ruff check src tests`
- `uv run lint-imports`

CI runs the full `uv run python -m pytest`. A pull request is not ready until that CI run is green.

Project memory: before work, search Supermemory (containerTag `repo_finance_analysis_service__8f4d8448ee5d9b71`) for the root entry «FAS память проекта: оглавление», the project map, and decisions. After work, write the outcome there: what changed, decisions, and open questions. Do not duplicate existing entries.

Import boundary is `[tool.importlinter]` in pyproject.toml: adapters, then application, then domain. `finance_analysis.plugins` does not import adapters or application. No `requests` in the service. `lint-imports` checks this. Do not copy that layer text here.

Do not commit `.env` or secrets. Do not hand-edit `uv.lock`.

Product spec: `docs/design-v0.23.md`. Run details: `README.md`. Do not copy them into this file.

Test-driven development: write the test before implementation code.

Ponytail full: smallest complete change.

The author does not approve or merge their own pull request.

Role routing, models, and the tracker live in this Project's Context, not in this file.
