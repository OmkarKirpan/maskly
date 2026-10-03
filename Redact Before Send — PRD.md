# Redact Before Send — PRD

## Overview

Redact Before Send is an offline desktop tool that blacks out personal data in screenshots before a support agent shares them. It runs Gemma 4 E4B on the agent's own laptop, so customer data never leaves the device.

**Problem.** Support agents paste customer screenshots into tickets, Slack threads and vendor escalations many times a day. Those screenshots often contain emails, phone numbers, card digits, addresses, API keys and faces. Manual redaction is slow and easy to get wrong, and cloud redaction tools send the same data to yet another server.

**Why now.** Gemma 4 edge models understand images and run offline on ordinary laptops. India's DPDP Act raises the cost of leaking personal data. Pattern-only tools miss context, such as a name sitting in a "Customer" column.

## Goals and non-goals

The hackathon MVP succeeds if it redacts a screenshot offline in under 5 seconds and catches at least 90% of sensitive items.

**Goals**

- Redact a typical 1080p screenshot in under 5 seconds on a 16 GB laptop, with no internet.
- Catch at least 90% of sensitive items (recall) with at least 80% precision on the test set.
- Let the agent review and adjust every box before anything is copied.
- Never output an unredacted image silently.

**Non-goals for the MVP**

- Video, audio, PDFs and live screen sharing (see Roadmap).
- A mobile app.
- Accounts, cloud sync or team servers.
- Certifying legal compliance. The tool supports compliance; it does not guarantee it.

## Users

The primary user is the support agent; leads and security teams decide whether it gets adopted.

| Persona | Core need | Success looks like |
| --- | --- | --- |
| Support agent (primary) | Share customer screenshots fast without leaking data | One paste, few false boxes, redacted copy in seconds |
| Support lead | Consistent redaction across the whole team | Shared profiles and allowlist, simple usage counts |
| Security or compliance reviewer | Proof that personal data stays in-house | No network calls, local audit log with counts only |

## User stories

Seven stories define the MVP; the first three are the core loop.

- As a support agent, I paste a customer screenshot and get a redacted copy on my clipboard within seconds.
- As a support agent, I see why each box was drawn and remove a false one with one click.
- As a support agent, I draw a box by hand over anything the tool missed.
- As a support lead, I pick a profile such as "external ticket" or "internal chat" so the team redacts consistently.
- As a support lead, I allowlist our own support email and domain so they are never blacked out.
- As a security reviewer, I confirm the app makes no network calls while running.
- As a security reviewer, I see counts of what was redacted by category, never the content itself.

## MVP scope

Eight P0 features make a complete, demoable loop: paste, detect, review, copy. P1 and P2 are added only if time allows.

| Feature | Priority | Notes |
| --- | --- | --- |
| Paste, drag-drop or file-pick a screenshot | P0 | Localhost web page for the MVP |
| OCR with word positions | P0 | PaddleOCR or Tesseract; each word gets an ID |
| Rules engine | P0 | Emails, phones, cards, Aadhaar, PAN, IFSC, API keys, IPs |
| Gemma 4 E4B context classifier | P0 | Picks sensitive word IDs that rules can't judge |
| Solid-fill redaction and metadata strip | P0 | Opaque boxes, never blur |
| Review screen | P0 | Toggle, remove or draw boxes before copying |
| Copy to clipboard or save file | P0 | PNG with a "\_redacted" suffix |
| Fail-closed partial-scan warning | P0 | Rules still apply if Gemma fails |
| Face and QR code detection | P1 | OpenCV or MediaPipe |
| Policy profiles and allowlist | P1 | "External ticket" vs "internal chat" |
| Local audit log | P1 | Counts by category only |
| Desktop app with global hotkey | P2 | GPUI Kit native app, replaces the web page |
| Text-only AI privacy gateway demo | P2 | Stretch demo of the 10x vision |

## Functional requirements

The tool detects 14 categories of sensitive data using three detectors, then lets a human approve the result.

**Detection coverage**

| Category | Detected by | Example |
| --- | --- | --- |
| Email address | Rules | priya@example.com |
| Phone number | Rules | +91 98xxx xxxxx |
| Card number | Rules with Luhn check | 16-digit card numbers |
| Aadhaar number | Rules with Verhoeff check | 12-digit ID |
| PAN | Rules | ABCDE1234F format |
| Bank details | Rules and Gemma | IFSC codes, account numbers |
| Secrets | Rules | AWS keys, GitHub tokens, JWTs, private keys |
| IP address | Rules | IPv4 and IPv6 |
| Person name | Gemma | Name in a "Customer" field |
| Postal address | Gemma | Street, city, PIN code |
| Customer or order ID | Gemma | ID next to "Order #" or "Account" |
| Internal URL or hostname | Gemma and rules | admin.company.internal |
| Face or profile photo | Visual detector | Avatars, ID photos |
| QR code | Visual detector | Payment QR codes |

**Input**

- FR-1: Accept PNG and JPG by paste, drag-drop or file picker.
- FR-2: Handle images up to 4K resolution.

**Detection**

- FR-3: OCR returns each word's text, bounding box and a unique ID.
- FR-4: Rules run on full line text, so numbers split by spaces are still caught, then map back to word boxes.
- FR-5: Gemma receives the image plus the numbered word list and returns JSON: word IDs, category, confidence and a short reason.
- FR-6: Gemma may only reference word IDs that exist; any unknown ID is discarded.
- FR-7: The visual detector returns boxes for faces and QR codes.

**Policy**

- FR-8: Rule matches are always redacted.
- FR-9: Gemma matches are redacted at or above a confidence threshold, default 0.6 and configurable.
- FR-10: Profiles set which categories apply, such as "external ticket" (strict) or "internal chat" (lighter).
- FR-11: An allowlist of exact strings and domains is never redacted.

**Redaction**

- FR-12: Apply solid opaque fill with 4 px padding; never blur or pixelate.
- FR-13: Flatten the output so original pixels under boxes are gone, and strip EXIF and other metadata.

**Review**

- FR-14: Show every box colored by detector, with category and reason on hover.
- FR-15: Let the user toggle, delete or draw boxes; approve with one keyboard shortcut.

**Output**

- FR-16: Copy the redacted image to the clipboard or save it as PNG with a "\_redacted" suffix.
- FR-17: Write a local audit entry: timestamp, profile and counts per category, never content.

## Non-functional requirements

The two non-negotiables are fully offline operation and failing closed; speed and accuracy figures are targets to validate in the first day of building.

| Area | Requirement |
| --- | --- |
| Privacy | No network calls at runtime; the app works with Wi-Fi off; model and processing stay on the device |
| Fail-closed | If OCR or Gemma fails or passes a 10-second timeout, apply rule and visual redactions, show a "partial scan" banner and require explicit confirmation to copy |
| Latency | Median under 5 seconds and 95th percentile under 10 seconds per 1080p screenshot on a 16 GB laptop without a GPU (target) |
| Accuracy | Recall at least 90% and precision at least 80% on the test set (target) |
| Memory | Peak RAM under 8 GB including the model (target; verify the quantized E4B footprint) |
| Data handling | The original screenshot stays in memory only, with no temp files on disk, and is discarded after export |
| Platform | Windows and macOS laptops; localhost web UI for the MVP |
| Usability | The full flow takes three actions: paste, review, copy |

## System architecture

Three predictable detectors find exact positions, and Gemma only chooses among words that OCR already found, so it can never place a box in the wrong spot.

&#91;embedded content: Redact Before Send pipeline · 8 components, all on-device\]

If Gemma fails or times out, the rule and visual redactions still apply and the review screen shows a partial-scan warning.

**Gemma output contract.** Gemma returns only JSON that the backend validates against a schema before use:

```json
{"findings": [{"word_ids": [14, 15], "category": "person_name", "confidence": 0.86, "reason": "Name in Customer field"}]}
```

**Tech stack**

| Layer | Choice |
| --- | --- |
| Model runtime | Ollama running a quantized Gemma 4 E4B |
| OCR | PaddleOCR or Tesseract |
| Visual detection | OpenCV for QR codes, MediaPipe for faces |
| Rendering | Pillow |
| Backend | Python with FastAPI on localhost |
| Frontend | Plain HTML and JavaScript page |
| Stretch | Native Rust app built with GPUI Kit 0.6, plus a global hotkey |

## Success metrics and evaluation

The MVP passes if it reaches 90% recall in under 5 seconds on a 50-screenshot test set, and if adding Gemma measurably beats rules alone.

**Test set.** Build 50 synthetic screenshots from fake data generated with a library such as Faker: support dashboards, chat windows, invoices, error pages and terminal logs. Hand-label every sensitive item with its box and category. Never use real customer data.

| Metric | Definition | Target |
| --- | --- | --- |
| Recall | Labeled sensitive items fully covered ÷ all labeled items | 90% or more |
| Precision | Correct boxes ÷ all boxes drawn | 80% or more |
| Leak rate | Screenshots with at least one missed item | 10% or less |
| Latency | Time from paste to review screen, median and 95th percentile | Under 5 s and under 10 s |
| Review effort | Boxes the user adds or removes per screenshot | 1 or fewer on average |

**Ablation.** Report recall for rules alone versus rules plus Gemma. That gap is the proof that Gemma adds real value, and it is the strongest chart for judges.

## Risks and mitigations

The biggest risk is a missed item that the agent trusts was caught, so human review stays mandatory.

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Agent assumes the tool catches everything | High | Review screen is mandatory; product copy says "assist, not guarantee" |
| OCR misreads small or stylized text | High | Upscale 2x before OCR; test on dense support UIs; manual box tool |
| Blurred text gets reconstructed | High | Solid fill only, never blur or pixelate |
| Gemma misses context or invents findings | Medium | Rules always apply; Gemma can only pick existing word IDs; confidence threshold |
| Too slow on a laptop | Medium | Fall back to E2B; skip words already matched by rules; keep the model loaded |
| False positives annoy agents | Medium | Allowlist, profiles and one-click removal |
| Numbers split across OCR boxes | Medium | Run rules on full line text and map matches back to words |
| E4B memory use too high on target laptops | Medium | Benchmark on day 1; use a quantized build |

## Roadmap

The MVP proves the on-device detection core; every later phase points that same core at a bigger surface.

&#91;embedded content: Roadmap · 4 phases from MVP to OS layer\]

The 10x gateway is the commercial prize: employees paste customer data into cloud AI daily, and the gateway keeps that data on the device while the AI still answers.

## Hackathon build plan and demo

The MVP fits a two-day build: pipeline on day 1, review screen and evaluation on day 2.

**Build plan**

1. Day 1 morning: install Ollama with Gemma 4 E4B and benchmark speed and memory; pick the OCR engine; generate the 50 test screenshots.
2. Day 1 afternoon: build OCR, the rules engine and the Gemma classifier with its JSON schema; return merged boxes from one API endpoint.
3. Day 1 evening: add solid-fill rendering, metadata stripping and the fail-closed path.
4. Day 2 morning: build the review screen with toggle, remove, draw and copy.
5. Day 2 afternoon: run the evaluation, including the rules-only versus rules-plus-Gemma comparison; add P1 features if time allows.
6. Day 2 evening: write the README with the architecture diagram, record a backup demo video and rehearse.

**Three-minute demo script**

1. State the problem in one line: agents share customer screenshots all day, and cloud tools mean the data leaves anyway.
2. Turn off Wi-Fi on stage.
3. Paste a busy support dashboard full of fake customer data.
4. Boxes appear in seconds; hover one to show Gemma's reason, such as "name in Customer field."
5. Remove one false box and draw one missed box to show the human stays in control.
6. Copy and paste into a mock ticket.
7. Show the ablation chart: rules alone versus rules plus Gemma.
8. Close on the 10x vision: "Today it cleans a screenshot. Tomorrow it's the privacy layer between every employee and every cloud."

## Open questions

Six decisions are still open; the first two should be settled by benchmarks on day 1.

- [ ] Does Gemma 4 E4B meet the 5-second and 8 GB targets on a 16 GB laptop, or is E2B needed?
- [ ] PaddleOCR or Tesseract: which is more accurate on dense support UIs at acceptable speed?
- [ ] Should Gemma see the full screenshot, or crops around each text region?
- [ ] What default confidence threshold balances recall and false positives?
- [ ] Which judging criteria does this hackathon weigh most: impact, technical depth or use of Gemma?
- [ ] GPUI Kit app: keep the Python pipeline as a local sidecar, or port it to Rust?
