# Contributing to afterprint-ai

## Setup

```bash
pip install uv
uv sync
cp .env.example .env
uv run uvicorn afterprint_ai.app:app --reload
```

## Workflow

1. Pick an issue from the [tracker](https://github.com/Afterprint/afterprint-ai/issues).
2. Branch from `main`: `git checkout -b feat/short-description`.
3. One logical change per commit, [Conventional Commits](https://www.conventionalcommits.org/) format: `type(scope): description`.
4. `uv run ruff check src/`, `uv run mypy src/ --ignore-missing-imports`, and `uv run pytest tests/ -v` must all pass before opening a PR.
5. Open a PR against `main`. CI must pass.

## Code standards

- `verify()` in `engine.py` is the integrity boundary: any claim in `VERIFIED_FACT`, `CORROBORATED_CLAIM`, or `CONFLICT` must have citations that actually resolve to real source spans, with matching quote/page/frame. Don't weaken this to make a test pass — weaken the test's expectations instead if it's genuinely wrong.
- New extraction logic should fail closed: if you can't confidently ground a claim in a source, return `UNKNOWN`, don't guess.
- Keep `pydantic` schemas (`schemas.py`) as the single source of truth for request/response shapes — don't duplicate shape validation elsewhere.

## Reporting a security issue

See [SECURITY.md](./SECURITY.md) — do not open a public issue for a vulnerability.
