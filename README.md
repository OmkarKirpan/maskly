# Maskly — Redact Before Send

Paste a customer screenshot, get a redacted copy. OCR + pattern rules + Gemma 4 run on your own machine.
Assist, not guarantee: you review every box before copying.

## Run

```bash
ollama pull gemma4:e2b        # or gemma4:e4b on a 16 GB machine
uv sync
uv run --env-file .env uvicorn app:app --port 8000   # open http://localhost:8000
```

Settings (env vars, kept in `.env`): `MASKLY_MODEL` (default `gemma4:e2b`), `MASKLY_OLLAMA` (default `http://localhost:11434`),
`MASKLY_TIMEOUT` (s, default 30), `MASKLY_THRESHOLD` (default 0.6).

**Cloud fallback (optional).** If local Ollama fails and `GEMINI_API_KEY` is set, Gemma 4 runs on the Gemini API
(`MASKLY_CLOUD_MODEL`, default `gemma-4-26b-a4b-it`; `MASKLY_CLOUD_TIMEOUT`, default 90 s). Rule matches are blacked out
before the image leaves the machine, and the page says the cloud was used. The free tier may keep and review inputs:
use fake data only.

If Gemma is missing, slow or fails, rule boxes still apply and the page shows a **partial scan** banner;
copy stays locked until you confirm you checked the image.

## Evaluate

```bash
uv run python samples.py   # fake screenshots + labels in samples/
uv run python eval.py      # recall/precision: rules only vs rules + Gemma
uv run python maskly.py    # rules self-check
```

See `Redact Before Send — PRD.md` for the full plan.
