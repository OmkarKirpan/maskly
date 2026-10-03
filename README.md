<div align="center">

# 🕶️ Maskly

**Redact before you send.**
Paste a customer screenshot and get a safe copy back in a few seconds. Emails, card numbers, names, addresses and API keys get blacked out by a Gemma 4 model running on your own laptop.

![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
![Gemma 4](https://img.shields.io/badge/model-Gemma%204-7b2cbf)
![Runs offline](https://img.shields.io/badge/runs-offline-black)

**[▶ Try the live demo](https://omkarkirpan.github.io/maskly/)** · saved results from a real run (scanning your own images needs the local app)

<img src="docs/before-after.png" alt="A support ticket screenshot before and after Maskly: name, email, phone, order ID, card and address are covered by solid black boxes" width="100%">

</div>

---

## The problem

Support agents paste customer screenshots into tickets, Slack threads and vendor escalations many times a day. Those screenshots are full of personal data. Redacting by hand is slow and easy to get wrong, and cloud redaction tools send the same data to yet another server.

**Maskly does the redaction on your own machine.** You paste a screenshot, check the boxes, and copy the safe version.

## How it works

Three detectors find exact positions. Gemma only **chooses among words OCR already found**, so it can never put a box in the wrong place.

```mermaid
flowchart LR
    A[📋 Paste screenshot] --> B[RapidOCR<br/>words + boxes]
    B --> C[Rules<br/>regex + Luhn + Verhoeff]
    B --> D[Gemma 4<br/>reads image + word list]
    C --> E[Merge boxes]
    D --> E
    E --> F[👀 You review<br/>toggle · draw]
    F --> G[⬛ Solid fill<br/>PNG to clipboard]
```

| Detector | What it catches | Why |
|---|---|---|
| **Rules** | Emails, phone numbers, card numbers (Luhn check), Aadhaar (Verhoeff check), PAN, IFSC, IPv4/IPv6, internal hostnames, AWS / GitHub / Slack / OpenAI keys, JWTs, private keys | Exact patterns. Fast. Always run. |
| **Gemma 4** | Names, postal addresses, order / customer / account IDs, bank account numbers | Needs context: a name in a "Customer" field, an ID next to "Order #". |
| **You** | Anything missed | One click turns a box off. Drag to draw a new one. |

Gemma returns strict JSON. Any word ID it makes up is thrown away:

```json
{"findings": [{"word_ids": [14, 15], "category": "person_name", "confidence": 0.86, "reason": "Name in Customer field"}]}
```

## Results

<img src="docs/results.png" alt="Bar chart: rules alone catch 67% of sensitive items; rules plus Gemma 4 catch 100%" width="600">

| | Items caught (recall) | Correct boxes (precision) | Screenshots with a leak |
|---|---|---|---|
| Rules only | 10 / 15 (67%) | 100% | 2 of 3 |
| **Rules + Gemma 4** | **15 / 15 (100%)** | 87% | **0 of 3** |

Measured on 3 synthetic screenshots (support ticket, KYC review, error log) made with fake [Faker](https://faker.readthedocs.io) data, with `gemma-4-26b-a4b-it`. It is a small test set, so treat it as a first signal. Reproduce it with `uv run python eval.py`.

### Speed

Local Gemma 4 is slow on small GPUs. Measured with `gemma4:e2b` on a laptop GTX 1650 (4 GB), fully on the GPU:

| | Gemma time per screenshot | Recall | Correct boxes (precision) | Screenshots with a leak |
|---|---|---|---|---|
| Thinking on (default) | 35–57 s | 15 / 15 (100%) | 69% | 0 of 3 |
| `MASKLY_THINK=0` | 9–19 s | 14 / 15 (93%) | 45–49% | 1 of 3 |

OCR and rules add 2–6 s. Most of Gemma's time is spent writing its hidden reasoning before the answer, about 700 of 1,000 output tokens. Shrinking the image barely helps, because reading the image takes about 5 s. The default timeout is 90 s so a slow scan can still finish; on a faster GPU you can lower it.

## Safety by design

- **Fail closed.** If Gemma is missing, slow or fails, the rule boxes still apply. A **partial scan** banner appears, and Copy stays locked until you confirm you checked the image.
- **Solid fill, never blur.** Blurred text can be rebuilt. Maskly draws opaque boxes and re-encodes the PNG, so no original pixels or EXIF data remain.
- **In memory only.** The server reads the image from the request body. It writes no temp files and keeps no logs of content.
- **Human in the loop.** Every box is shown with its category and reason before anything is copied. Maskly assists. It does not guarantee.

## Quick start

You need [uv](https://docs.astral.sh/uv/) and [Ollama](https://ollama.com).

```bash
git clone https://github.com/OmkarKirpan/maskly && cd maskly
ollama pull gemma4:e2b          # 4.6 GB · use gemma4:e4b on a 16 GB machine
uv sync
uv run uvicorn app:app --port 8000
```

Open **http://localhost:8000** and paste a screenshot (<kbd>⌘V</kbd>).

| Key | Action |
|---|---|
| <kbd>⌘V</kbd> / drop / **Open…** | Load a screenshot |
| Click a box | Turn it off or on |
| Drag | Draw a new box |
| <kbd>P</kbd> | Preview the redacted result |
| <kbd>⌘</kbd> <kbd>↵</kbd> | Copy the redacted PNG |

## Configuration

Put settings in a `.env` file and start with `uv run --env-file .env uvicorn app:app --port 8000`.

| Variable | Default | Meaning |
|---|---|---|
| `MASKLY_MODEL` | `gemma4:e2b` | Local Ollama model |
| `MASKLY_OLLAMA` | `http://localhost:11434` | Ollama server |
| `MASKLY_TIMEOUT` | `90` | Seconds before a local call counts as failed |
| `MASKLY_THINK` | `1` | Set `0` to turn off Gemma's thinking: 2–3× faster, but it misses more |
| `MASKLY_THRESHOLD` | `0.6` | Minimum Gemma confidence for a box |
| `GEMINI_API_KEY` | — | Turns on the cloud fallback (optional) |
| `MASKLY_CLOUD_MODEL` | `gemma-4-26b-a4b-it` | Gemini API model for the fallback |
| `MASKLY_CLOUD_TIMEOUT` | `90` | Seconds before a cloud call counts as failed |

### Cloud fallback

Campus Wi-Fi and small laptops don't always cooperate, so Maskly can fall back to Gemma 4 on the Gemini API. The fallback runs **only when local Ollama fails**. It follows these rules:

- Words the rules already caught are **blacked out in the image** and **left out of the word list** before anything is uploaded.
- The page tells you when the cloud was used.
- ⚠️ The Gemini API free tier may keep and review inputs. **Use fake data only** with the fallback.

## Use it from an AI agent

Maskly ships as an [Agent Skill](https://agentskills.io) in [`skills/redact-screenshot/`](skills/redact-screenshot/SKILL.md), so coding and support agents redact a screenshot **before** they attach or upload it.

```bash
cp -r skills/redact-screenshot ~/.claude/skills/      # or your agent's skills folder
```

The agent runs `uv run scripts/redact.py shot.png` and gets back `shot_redacted.png` plus a JSON report with **counts only, never the redacted text**, so personal data stays out of the agent's context too. Cloud fallback is off unless `--allow-cloud` is passed, and a partial scan exits with code `2` so the agent asks you to check before sharing. Validated with `skills-ref validate`.

The same pipeline is a CLI: `uv run maskly shot.png`.

## Evaluate it yourself

```bash
uv run python samples.py        # make fake screenshots + labels in samples/
uv run python eval.py           # recall and precision: rules only vs rules + Gemma
uv run python maskly.py         # rules self-check
```

## Project layout

```
maskly.py          OCR, rules, Gemma (local + cloud), detect(), redact(), `maskly` CLI
skills/            Agent Skill: redact-screenshot
app.py             FastAPI server: GET / and POST /detect
static/index.html  Review page: paste, review, copy (no build step)
static/tokens.css  Design tokens; fonts are bundled in static/fonts so it works offline
samples.py         Fake screenshots with labelled sensitive items
eval.py            Recall / precision, rules only vs rules + Gemma
make_demo.py       Saves real results for the GitHub Pages demo (demo/)
```

## Roadmap

- [x] OCR + rules + Gemma 4 pipeline, review page, fail-closed path
- [x] Gemini API fallback with rule-redacted upload
- [x] Benchmark local Gemma 4 E2B: 35–57 s per screenshot on a GTX 1650, so the 5-second target is not met (see [Speed](#speed))
- [ ] Benchmark E4B and faster GPUs; find a way to hit 5 seconds
- [ ] Face and QR code detection
- [ ] Team profiles ("external ticket" vs "internal chat") and an allowlist
- [ ] Local audit log with counts per category, never content
- [ ] Native desktop app with a global hotkey
- [ ] **Privacy gateway:** the same detector between every employee and every cloud AI

## Built with

[Gemma 4](https://ai.google.dev/gemma) · [Ollama](https://ollama.com) · [RapidOCR](https://github.com/RapidAI/RapidOCR) · [FastAPI](https://fastapi.tiangolo.com) · [Pillow](https://python-pillow.org) · [uv](https://docs.astral.sh/uv/)

Built for the **Best Use of Gemma 4** and **Best Open-Source AI Project** hackathon tracks. The full plan is in [`Redact Before Send — PRD.md`](./Redact%20Before%20Send%20—%20PRD.md).

## License

[MIT](LICENSE)
