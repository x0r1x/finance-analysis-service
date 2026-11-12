# Agent contract

Setup: Python 3.12 and `uv sync`, as in README.md. If uv is missing, `pip install -e ".[dev]"`, as in `.github/workflows/ci.yml`. Run the checks after install.

Before saying the work is done, run the same checks as `.github/workflows/ci.yml`. Done only when each exits 0. A truncated log is not green. While iterating, run the affected pytest file. Run the full three before the PR.

- `ruff check src tests`
- `lint-imports`
- `python -m pytest`

Import boundary is `[tool.importlinter]` in pyproject.toml: adapters, then application, then domain. `finance_analysis.plugins` does not import adapters or application. No `requests` in the service. `lint-imports` checks this. Do not copy that layer text here.

Do not commit `.env` or secrets. Do not hand-edit `uv.lock`.

Product spec: `docs/design-v0.23.md`. Run details: `README.md`. Do not copy them into this file.

Test-driven development: write the test before implementation code.

Ponytail full: smallest complete change.

The author does not approve or merge their own pull request.

Role routing, models, and the tracker live in this Project's Context, not in this file.
