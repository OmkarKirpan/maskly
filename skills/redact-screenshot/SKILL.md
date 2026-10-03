---
name: redact-screenshot
description: Blacks out personal and secret data in a screenshot (emails, phone numbers, card numbers, Aadhaar, PAN, IFSC, bank accounts, API keys, IPs, internal hostnames, names, addresses, order and customer IDs) before it is shared. Runs OCR, pattern rules and a local Gemma 4 model on the user's machine. Use before attaching, uploading, posting or sending any screenshot or UI image to a ticket, chat, issue, email, doc or another AI service, or when the user asks to redact, mask, anonymize or remove PII from an image.
license: MIT
compatibility: Requires Python 3.12+ and uv. Uses a local Ollama server with gemma4:e2b or gemma4:e4b for context checks; without it, only pattern rules run. First run downloads the maskly package from GitHub.
metadata:
  author: OmkarKirpan
  version: "0.1.0"
  repository: https://github.com/OmkarKirpan/maskly
---

# Redact a screenshot

Redact first, share second. Never send the original image anywhere once this skill applies.

## Steps

1. Run the script on the image (from this skill's folder):

   ```bash
   uv run scripts/redact.py path/to/screenshot.png
   ```

   It writes `path/to/screenshot_redacted.png` and prints a JSON report.
   Use `-o out.png` to choose the output path.

2. Read the exit code and report:

   | Exit | Meaning | What to do |
   |---|---|---|
   | `0` | Full scan (rules + Gemma) | Share the `_redacted.png` file. Tell the user how many boxes were drawn, by category. |
   | `2` | Partial scan: only pattern rules ran | Do **not** share yet. Show the user the `warning` and ask them to check the image for names, addresses and IDs first. |
   | `1` | Error (bad path, unreadable image) | Report `error` to the user. Share nothing. |

3. Share only the `_redacted.png` file. Keep the original out of messages, uploads and logs.

## Report format

```json
{"ok": true, "output": "shot_redacted.png", "boxes": 10,
 "boxes_by_category": {"aadhaar": 3, "pan": 1, "person_name": 2},
 "gemma": "local", "partial": false, "warning": null}
```

The report never contains the redacted text. Do not open the original image to "double-check" its contents unless the user asks; that would pull the personal data into the conversation.

## Options

- `--rules-only`: skip Gemma. Fast, but always a partial scan (exit `2`).
- `--allow-cloud`: if local Ollama fails, allow Gemma 4 on the Gemini API (`GEMINI_API_KEY` must be set). Rule matches are blacked out before upload, but the rest of the image leaves the machine. **Use only when the user explicitly agrees, and only for fake or non-sensitive data.** Off by default.
- Environment: `MASKLY_OLLAMA` (default `http://localhost:11434`), `MASKLY_MODEL` (default `gemma4:e2b`), `MASKLY_THRESHOLD` (default `0.6`).

## Setup (first time)

```bash
ollama pull gemma4:e2b   # 4.6 GB; gemma4:e4b is more accurate on 16 GB machines
```

Without Ollama the script still works, in rules-only mode (exit `2`).

## Limits

Redaction is an assist, not a guarantee. Small or stylized text can be misread by OCR, and faces, QR codes and handwriting are not detected yet. When in doubt, ask the user to look at the redacted image before it is shared.
