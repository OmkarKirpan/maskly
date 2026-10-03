# Gemma 4 E4B / E2B facts: Ollama and Google API

Resolves issue #3. Researched 2026-10-03 against primary sources. Anything not found in a first-party source is marked **unconfirmed**.

## Model basics (Google model card)

| | E2B | E4B |
|---|---|---|
| Parameters | 2.3B effective (5.1B with embeddings) | 4.5B effective (8B with embeddings) |
| Context | 128K | 128K |
| Modalities | Text, image, audio (video as frames) | Text, image, audio (video as frames) |
| Vision encoder | ~150M | ~150M |

- Image understanding explicitly covers OCR, document/PDF parsing, and screen and UI understanding. Images work at variable aspect ratio and resolution, with a configurable visual token budget of 70 / 140 / 280 / 560 / 1120 tokens. Google recommends putting the image before the text in the prompt. Source: [Gemma 4 model card](https://ai.google.dev/gemma/docs/core/model_card_4)
- Vision benchmarks (instruction-tuned): MMMU Pro E4B 52.6%, E2B 44.2%. OmniDocBench edit distance (lower is better) E4B 0.181, E2B 0.290. E2B is noticeably weaker at reading documents. Source: [model card](https://ai.google.dev/gemma/docs/core/model_card_4)

## Ollama

| Fact | Value | Source |
|---|---|---|
| Tags | `gemma4:e2b`, `gemma4:e4b` (`gemma4:latest` = e4b). Explicit quants: `e2b-it-qat`, `e2b-it-q4_K_M`, `e2b-it-q8_0`, `e2b-it-bf16`, and the same four for `e4b-it-*`. MLX variants `e2b-mlx` and `e4b-mlx` also exist. | [ollama.com/library/gemma4/tags](https://ollama.com/library/gemma4/tags) |
| Download sizes, E2B | qat 4.3 GB, q4_K_M 4.6 GB (default), q8_0 8.1 GB, bf16 10 GB | same |
| Download sizes, E4B | qat 6.1 GB, q4_K_M 6.6 GB (default), q8_0 12 GB, bf16 16 GB | same |
| Vision input in Ollama | Yes. Every gemma4 tag lists "Text, Image" input. Audio is **not** listed as an Ollama input. | same |
| JSON / structured output | Yes, through Ollama's generic `format` parameter (`"json"` or a JSON schema) on `/api/chat` and `/api/generate`. This is model-agnostic; I found no gemma4-specific test. Ollama's docs say it does **not** apply to Ollama Cloud (`gemma4:cloud`). | [Ollama structured outputs doc](https://github.com/ollama/ollama/blob/main/docs/capabilities/structured-outputs.mdx) |
| RAM footprint | Google publishes weights-only memory figures. E2B: 2.9 GB at Q4_0, 5.7 GB at 8-bit, 11.4 GB at BF16. E4B: 4.5 GB at Q4_0, 8.9 GB at 8-bit, 17.9 GB at BF16. KV cache and runtime come on top. Ollama does not publish a resident-RAM figure (**unconfirmed**). The download size is a practical lower bound for RAM: about 6.6 GB for E4B q4_K_M and 4.6 GB for E2B. | [Gemma core docs, memory table](https://ai.google.dev/gemma/docs/core) |

## Published speeds

Neither Google nor Ollama publishes laptop speed numbers, so **no first-party figures exist**. The best third-party measurement I found states its hardware, Ollama version and tags. It uses text-only prompts with no image timing ([ai-muninn benchmark](https://ai-muninn.com/en/blog/dgx-spark-gemma4-e2b-vs-e4b-ollama-3-machines)):

| Machine | E2B gen / prefill tok/s | E4B gen / prefill tok/s |
|---|---|---|
| M1 Max 32 GB, Ollama 0.20.3 | 81 / 507 | 52 / 309 |
| M4 16 GB, Ollama 0.20.0 | 42 / 390 | 23 / 230 |

- **CPU-only 16 GB laptop: unconfirmed.** The only figure I found was an unsourced "~2–5 tok/s for E4B" on a non-primary site, so I am not relying on it.
- **Image-prefill latency: unconfirmed.** No published number covers a screenshot as input. The local benchmark has to measure it.

## Google AI (Gemini API) cloud fallback

| Fact | Value | Source |
|---|---|---|
| Same model available? | **No.** The Gemini API serves only `gemma-4-31b-it` and `gemma-4-26b-a4b-it`. E2B and E4B are not offered. | [Run Gemma with the Gemini API](https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api) |
| Image input | Yes. The doc includes image examples (inline data and Files API) for the Gemma 4 API models. | same |
| Other API features | System instructions, function calling, toggleable thinking (`thinking_level`) | same |
| JSON / structured output via API | **Unconfirmed.** The Gemma-on-API page and the structured-output doc do not list Gemma. Test `response_mime_type`/`response_schema`, or fall back to prompt-and-parse. | [structured output doc](https://ai.google.dev/gemini-api/docs/structured-output) |
| Price | Free tier: "Free of charge". Paid tier: "Not available". | [Gemini API pricing, Gemma 4 section](https://ai.google.dev/gemini-api/docs/pricing) |
| Rate limits / quota | **Unconfirmed.** The rate-limits page has no Gemma numbers. It says limits are shown per project in AI Studio. | [Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) |
| Data use | The pricing table lists "Used to improve our products: Yes" for the free tier. The Unpaid Services terms let Google use submitted content to improve its products, allow human reviewers to read inputs and outputs, and tell users not to submit sensitive, confidential or personal information. Paid services are not used for training and keep logs only for a limited period for abuse detection, but Gemma has **no paid tier**. Exception: users in the EEA, UK or Switzerland get Paid-Services data handling even on the free tier. | [Gemini API terms](https://ai.google.dev/gemini-api/terms), [pricing](https://ai.google.dev/gemini-api/docs/pricing) |

## What this means for the benchmark and fallback decisions

1. Benchmark `gemma4:e4b` (q4_K_M, 6.6 GB) as the primary model and `gemma4:e2b` as the low-RAM option. E2B fits a 16 GB laptop easily but reads documents and UIs much worse. Time image prefill ourselves, because no published number covers it and none covers CPU-only machines.
2. The cloud fallback cannot use the same model. It would be `gemma-4-26b-a4b-it` (or 31b), so prompts, output parsing and JSON enforcement must be checked separately on that model.
3. The cloud fallback is free-tier only. Prompts and screenshots may be used for training and read by human reviewers, and the terms say not to send personal data. For a redaction tool, the fallback must never send the unredacted screenshot. At most it should be opt-in with an explicit warning, or limited to non-sensitive inputs.
