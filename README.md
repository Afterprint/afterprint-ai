<p align="center">
  <img src="https://raw.githubusercontent.com/Afterprint/afterprint-web/main/public/afterprint-logo.png" width="72" alt="Afterprint logo" />
</p>

<h1 align="center">Afterprint — AI</h1>

<p align="center">
  Conservative, citation-grounded evidence analysis: source extraction, transcription, timeline/graph building, and conflict detection — with every claim traceable back to a specific source span.
</p>

<p align="center">
  <a href="https://github.com/Afterprint/afterprint-ai/actions/workflows/ci.yml"><img src="https://github.com/Afterprint/afterprint-ai/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/runtime-Python%203.13-3776AB" alt="Python 3.13">
  <img src="https://img.shields.io/badge/framework-FastAPI-009688" alt="FastAPI">
  <img src="https://img.shields.io/github/license/Afterprint/afterprint-ai" alt="License">
</p>

---

## What this service does

`afterprint-ai` is an internal service — every route requires a shared bearer token from [`afterprint-api`](https://github.com/Afterprint/afterprint-api), it's never called directly by the web app. It:

- Extracts text from evidence (OCR via Tesseract for images/PDFs, Whisper transcription via Groq for audio/video)
- Groups extracted claims into categories (`VERIFIED_FACT`, `CORROBORATED_CLAIM`, `INFERENCE`, `CONFLICT`, `UNKNOWN`) and **refuses to emit a grounded claim without a citation** pointing back to the exact source span
- Builds a timeline and entity graph across all evidence in a case
- Flags candidate conflicts: sources sharing an entity label with differing time claims

The design principle: this service should never let the AI assert something it can't point back to a source for. `UNKNOWN` is a valid, expected answer.

## Quick start

```bash
pip install uv
uv sync
cp .env.example .env   # AI_SERVICE_TOKEN, SPEECH_API_KEY (Groq), EVIDENCE_STORAGE_HOSTS
uv run uvicorn afterprint_ai.app:app --reload
```

```bash
uv run ruff check src/
uv run mypy src/ --ignore-missing-imports
uv run pytest tests/ -v
```

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the workflow and coding standards, and [SECURITY.md](./SECURITY.md) to report a vulnerability privately.

## Maintainer

| | |
|---|---|
| **GitHub** | [@helloworld1-star](https://github.com/helloworld1-star) |
| **Email** | chijiokejoseph20242@gmaill.com |

---

<p align="center">
  <a href="https://github.com/Afterprint/afterprint-ai/graphs/contributors">
    <img src="https://contrib.rocks/image?repo=Afterprint/afterprint-ai" alt="Contributors" />
  </a>
</p>
