"""Detection pipeline: OCR -> rules -> Gemma. Returns boxes; redaction happens in the browser."""
import base64
import io
import json
import os
import re
import time

import httpx
from PIL import ImageDraw

MODEL = os.environ.get("MASKLY_MODEL", "gemma4:e2b")
OLLAMA = os.environ.get("MASKLY_OLLAMA", "http://localhost:11434")
# PRD says 10 s, but local Gemma 4 thinks first: E2B on a GTX 1650 takes 35-57 s per screenshot.
TIMEOUT = float(os.environ.get("MASKLY_TIMEOUT", "90"))
# Thinking off is 2-3x faster but misses more (eval: recall 100% -> 93%, precision 69% -> ~47%).
THINK = os.environ.get("MASKLY_THINK", "1") != "0"
THRESHOLD = float(os.environ.get("MASKLY_THRESHOLD", "0.6"))
# Cloud fallback, used only when local Ollama fails. Free-tier Gemini API: fake data only.
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
CLOUD_MODEL = os.environ.get("MASKLY_CLOUD_MODEL", "gemma-4-26b-a4b-it")
# Cloud Gemma 4 always "thinks" first (~40 s per screenshot); its thinking cannot be turned off.
CLOUD_TIMEOUT = float(os.environ.get("MASKLY_CLOUD_TIMEOUT", "90"))

# ---------------------------------------------------------------- OCR

_ocr = None


def ocr(img):
    """Return (words, lines). word = {id, text, box[x0,y0,x1,y1]}; line = [word ids]."""
    global _ocr
    if _ocr is None:
        from rapidocr import RapidOCR
        _ocr = RapidOCR()
    import numpy as np
    res = _ocr(np.array(img), return_word_box=True)
    words, lines = [], []
    for line in res.word_results or []:  # one entry per text line: [(word, score, quad), ...]
        ids = []
        for text, _score, quad in line:
            q = np.array(quad, dtype=float).reshape(-1, 2)
            words.append({"id": len(words), "text": text,
                          "box": [q[:, 0].min(), q[:, 1].min(), q[:, 0].max(), q[:, 1].max()]})
            words[-1]["box"] = [float(v) for v in words[-1]["box"]]
            ids.append(words[-1]["id"])
        lines.append(ids)
    return words, lines

# ---------------------------------------------------------------- rules


def luhn(digits):
    s = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch) * (2 if i % 2 else 1)
        s += d - 9 if d > 9 else d
    return s % 10 == 0


_D = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5], [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
      [3, 4, 0, 1, 2, 8, 9, 5, 6, 7], [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
      [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3], [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
      [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
_P = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4], [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
      [8, 9, 1, 6, 0, 4, 3, 5, 2, 7], [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
      [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]


def verhoeff(digits):
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def verhoeff_digit(digits):
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return str([0, 4, 3, 2, 1, 5, 6, 7, 8, 9][c])


def _digits(s):
    return re.sub(r"\D", "", s)


RULES = [  # (category, regex, optional check on the matched text)
    ("email", r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", None),
    ("card", r"\b(?:\d[ -]?){12,18}\d\b", lambda m: 13 <= len(_digits(m)) <= 19 and luhn(_digits(m))),
    ("aadhaar", r"\b[2-9]\d{3}[ -]?\d{4}[ -]?\d{4}\b", lambda m: verhoeff(_digits(m))),
    ("pan", r"\b[A-Z]{5}\d{4}[A-Z]\b", None),
    ("bank_details", r"\b[A-Z]{4}0[A-Z0-9]{6}\b", None),  # IFSC
    ("phone", r"(?:\+91[ -]?|\b0)?\b[6-9]\d{4}[ -]?\d{5}\b", None),
    ("phone", r"\+\d{1,3}[ -]?\(?\d{1,4}\)?(?:[ -]?\d{2,5}){2,4}\b", None),
    ("phone", r"\(?\b\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b", None),
    ("secret", r"\bAKIA[0-9A-Z]{16}\b|\bgh[pousr]_[A-Za-z0-9]{30,}|\bsk-[A-Za-z0-9_-]{20,}"
               r"|\beyJ[\w-]{8,}\.[\w-]{8,}\.[\w-]{8,}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
               r"|\bxox[abp]-[A-Za-z0-9-]{10,}", None),
    ("ip_address", r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b", None),
    ("ip_address", r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b|\b(?:[0-9a-fA-F]{1,4}:){2,6}:[0-9a-fA-F:]*", None),
    ("internal_url", r"\b[\w-]+(?:\.[\w-]+)*\.(?:internal|local|corp|lan|intranet)\b", None),
]


def rules(words, lines):
    """Run regexes on full line text (catches numbers split by spaces), map hits back to word ids."""
    hits = {}
    for ids in lines:
        text, spans = "", []
        for i in ids:
            if text:
                text += " "
            spans.append((len(text), len(text) + len(words[i]["text"]), i))
            text += words[i]["text"]
        for cat, rx, check in RULES:
            for m in re.finditer(rx, text):
                if check and not check(m.group()):
                    continue
                for s, e, i in spans:
                    if s < m.end() and m.start() < e:
                        hits.setdefault(i, cat)
    return hits

# ---------------------------------------------------------------- Gemma

CATEGORIES = ["person_name", "postal_address", "customer_or_order_id", "bank_details",
              "internal_url", "email", "phone", "other_personal"]
SCHEMA = {"type": "object", "required": ["findings"], "properties": {"findings": {"type": "array", "items": {
    "type": "object", "required": ["word_ids", "category", "confidence", "reason"],
    "properties": {"word_ids": {"type": "array", "items": {"type": "integer"}},
                   "category": {"type": "string", "enum": CATEGORIES},
                   "confidence": {"type": "number"}, "reason": {"type": "string"}}}}}}
PROMPT = """You help a support agent redact a screenshot before sharing it.
OCR found these words, one per line as `id: text`:
{words}

Return every word that is personal or confidential data about a customer or the company:
person names, postal addresses, PIN codes, customer / order / account / ticket IDs,
bank account numbers, internal hostnames or URLs, and other personal data.
Do NOT return field labels (like "Name:" or "Order #"), button text, or generic UI words.
Group the words of one item in one finding. Use only ids from the list.
confidence is 0..1. reason is under 8 words, e.g. "Name in Customer field"."""


def _png_b64(img):
    small = img.copy()
    small.thumbnail((1280, 1280))
    buf = io.BytesIO()
    small.save(buf, "PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _ask_local(prompt, img):
    r = httpx.post(f"{OLLAMA}/api/chat", timeout=TIMEOUT, json={
        "model": MODEL, "stream": False, "format": SCHEMA, "keep_alive": "30m", "think": THINK, "options": {"temperature": 0},
        "messages": [{"role": "user", "images": [_png_b64(img)], "content": prompt}]})
    r.raise_for_status()
    return r.json()["message"]["content"]


def _ask_cloud(prompt, img):
    r = httpx.post(f"https://generativelanguage.googleapis.com/v1beta/models/{CLOUD_MODEL}:generateContent",
                   headers={"x-goog-api-key": GEMINI_KEY}, timeout=CLOUD_TIMEOUT, json={
                       "contents": [{"parts": [{"text": prompt + "\nReply with JSON only: " + json.dumps(SCHEMA)},
                                               {"inline_data": {"mime_type": "image/png", "data": _png_b64(img)}}]}],
                       "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}})
    r.raise_for_status()
    # Gemma returns thinking parts first; the answer is the last {...} block.
    text = "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"] if not p.get("thought"))
    return text[text.find("{"):text.rfind("}") + 1]


def gemma(img, words, skip):
    """Ask Gemma which words are sensitive -> (findings, backend). Raises if every backend fails."""
    todo = [w for w in words if w["id"] not in skip]
    if not todo:
        return [], "none"
    prompt = PROMPT.format(words="\n".join(f"{w['id']}: {w['text']}" for w in todo))
    try:
        raw, backend = _ask_local(prompt, img), "local"
    except Exception:
        if not GEMINI_KEY:
            raise
        # Cloud never sees what rules already caught: black those words out first.
        safe = img.copy()
        d = ImageDraw.Draw(safe)
        for w in words:
            if w["id"] in skip:
                x0, y0, x1, y1 = w["box"]
                d.rectangle([x0 - 4, y0 - 4, x1 + 4, y1 + 4], fill="black")
        raw, backend = _ask_cloud(prompt, safe), "cloud"
    valid = {w["id"] for w in todo}
    out = []
    for f in json.loads(raw).get("findings", []):
        ids = [i for i in f.get("word_ids", []) if isinstance(i, int) and i in valid]  # FR-6: drop invented ids
        if ids and float(f.get("confidence", 0)) >= THRESHOLD:
            out.append({**f, "word_ids": ids})
    return out, backend

# ---------------------------------------------------------------- pipeline


def detect(img, use_gemma=True):
    t = time.perf_counter()
    words, lines = ocr(img)
    hits = rules(words, lines)
    boxes = [{"box": words[i]["box"], "text": words[i]["text"], "source": "rules", "category": c,
              "reason": "Pattern match", "confidence": 1.0} for i, c in hits.items()]
    partial, error, backend = False, None, "off"
    t_ocr = time.perf_counter()
    if use_gemma:
        try:
            findings, backend = gemma(img, words, hits)
            for f in findings:
                boxes += [{"box": words[i]["box"], "text": words[i]["text"], "source": "gemma",
                           "category": f["category"], "reason": f["reason"],
                           "confidence": round(float(f["confidence"]), 2)} for i in f["word_ids"]]
        except Exception as e:  # fail closed: rules still apply, UI shows partial-scan banner
            partial, error, backend = True, f"{type(e).__name__}: {e}"[:200], "failed"
    return {"width": img.width, "height": img.height, "boxes": boxes, "partial": partial, "error": error,
            "backend": backend,
            "words": len(words), "ms": {"ocr_rules": round((t_ocr - t) * 1000),
                                        "gemma": round((time.perf_counter() - t_ocr) * 1000)}}


def redact(img, boxes):
    """Solid black fill over every box; same padding as the web UI (4 px, or 20% of text height)."""
    out = img.convert("RGB")  # fresh pixels, no EXIF carried into the PNG
    d = ImageDraw.Draw(out)
    for b in boxes:
        x0, y0, x1, y1 = b["box"]
        p = max(4, (y1 - y0) * 0.2)
        d.rectangle([x0 - p, y0 - p, x1 + p, y1 + p], fill="black")
    return out


def cli(argv=None):
    """`maskly in.png` -> in_redacted.png + a JSON report with counts only (never the redacted text).
    Exit 0 = full scan, 2 = partial scan (rules only; a human must check), 1 = error."""
    import argparse
    from collections import Counter
    from pathlib import Path

    from PIL import Image

    global GEMINI_KEY
    ap = argparse.ArgumentParser(prog="maskly", description="Black out personal data in a screenshot, on this machine.")
    ap.add_argument("image", help="PNG or JPG to redact")
    ap.add_argument("-o", "--output", help="output PNG (default: <name>_redacted.png next to the input)")
    ap.add_argument("--rules-only", action="store_true", help="skip Gemma; pattern rules only (fast, misses names/addresses)")
    ap.add_argument("--allow-cloud", action="store_true",
                    help="allow the Gemini API fallback when local Ollama fails (free tier: fake data only)")
    a = ap.parse_args(argv)
    if not a.allow_cloud:
        GEMINI_KEY = ""  # safe default for agents: nothing leaves the machine
    src = Path(a.image)
    out = Path(a.output) if a.output else src.with_name(f"{src.stem}_redacted.png")
    try:
        if out.resolve() == src.resolve():
            raise ValueError("output would overwrite the input")
        img = Image.open(src).convert("RGB")
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}))
        return 1
    r = detect(img, use_gemma=not a.rules_only)
    redact(img, r["boxes"]).save(out, "PNG")
    partial = r["partial"] or a.rules_only
    print(json.dumps({
        "ok": True, "output": str(out), "boxes": len(r["boxes"]),
        "boxes_by_category": dict(Counter(b["category"] for b in r["boxes"])),
        "gemma": r["backend"], "partial": partial,
        "warning": "Partial scan: only pattern rules ran. Names, addresses and IDs may be visible. "
                   "Ask the user to check the image before sharing." if partial else None}, indent=1))
    return 2 if partial else 0


if __name__ == "__main__":  # self-check for the rules engine
    assert luhn("4111111111111111") and not luhn("4111111111111112")
    a = "23456789012"
    a += verhoeff_digit(a)
    assert verhoeff(a) and not verhoeff(a[:-1] + str((int(a[-1]) + 1) % 10))
    line = f"Mail priya@example.com card 4111 1111 1111 1111 aadhaar {a[:4]} {a[4:8]} {a[8:]} PAN ABCDE1234F " \
           "IFSC HDFC0001234 ph +91 98765 43210 ip 10.0.0.12 key AKIAIOSFODNN7EXAMPLE host db1.prod.internal ok"
    ws = [{"id": i, "text": t, "box": [0, 0, 1, 1]} for i, t in enumerate(line.split())]
    got = {ws[i]["text"]: c for i, c in rules(ws, [[w["id"] for w in ws]]).items()}
    for t in ["priya@example.com", "4111", "ABCDE1234F", "HDFC0001234", "98765", "10.0.0.12",
              "AKIAIOSFODNN7EXAMPLE", "db1.prod.internal", a[:4]]:
        assert t in got, (t, got)
    for t in ["Mail", "card", "ok", "PAN"]:
        assert t not in got, (t, got)
    print("rules ok:", got)
    from PIL import Image
    red = redact(Image.new("RGB", (100, 40), "white"), [{"box": [20, 10, 60, 30]}])
    assert red.getpixel((40, 20)) == (0, 0, 0) and red.getpixel((95, 5)) == (255, 255, 255)
    print("redact ok")
