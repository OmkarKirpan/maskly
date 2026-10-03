"""Score detectors on generated screenshots.
  --set ui        support-tool screenshots from uiset.py: the ship gate. --split tune = seeds 0+, test = seeds 1000+
  --set nemotron  NVIDIA Nemotron-PII (CC BY 4.0) test text rendered as documents: a stress test. Get the data:
                  curl -L -o data/nemotron-pii-test.parquet \\
                  https://huggingface.co/datasets/nvidia/Nemotron-PII/resolve/main/data/test-00000-of-00001.parquet
Run: uv run python bench.py [--set ui] [--split tune] [--n 60] [--detectors rules,gemma] [--gemma-n 6]"""
import argparse
import ast
import random
import time
from pathlib import Path

import pyarrow.parquet as pq
from PIL import Image, ImageDraw, ImageFont

import maskly
import uiset
from eval import covered, overlaps

DATA = Path(__file__).parent / "data" / "nemotron-pii-test.parquet"
SANS = next(f for f in ["/System/Library/Fonts/Helvetica.ttc", "C:/Windows/Fonts/arial.ttf",
                        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"] if Path(f).exists())
MONO = next(f for f in ["/System/Library/Fonts/Menlo.ttc", "C:/Windows/Fonts/consola.ttf",
                        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"] if Path(f).exists())
W, MARGIN, SIZE, LEADING, MAX_LINES = 1600, 40, 22, 34, 30

# Nemotron label -> must Maskly black it out? Labels in IGNORE are neither required (recall) nor
# penalised when boxed (precision): a support agent may or may not want a city or a date hidden.
SENSITIVE = {
    "first_name", "last_name", "email", "phone_number", "fax_number", "street_address", "postcode",
    "customer_id", "account_number", "employee_id", "user_name", "medical_record_number",
    "health_plan_beneficiary_number", "unique_id", "device_identifier", "vehicle_identifier", "license_plate",
    "certificate_license_number", "credit_debit_card", "cvv", "pin", "bank_routing_number", "swift_bic",
    "ssn", "national_id", "tax_id", "password", "api_key", "http_cookie", "ipv4", "ipv6", "mac_address",
    "date_of_birth", "biometric_identifier", "coordinate",
}


def wrap(text, font, maxw):
    """-> [(start, end)] character ranges of each rendered line, greedy word wrap, newlines respected."""
    out, pos = [], 0
    for para in text.split("\n"):
        start = pos
        while True:
            if font.getlength(text[start:pos + len(para)]) <= maxw:
                out.append((start, pos + len(para)))
                break
            end = start
            for i in range(start + 1, pos + len(para) + 1):
                if (i == pos + len(para) or text[i] == " ") and font.getlength(text[start:i]) <= maxw:
                    end = i
            if end == start:  # one very long token: hard cut
                end = next(i for i in range(start + 1, pos + len(para)) if font.getlength(text[start:i + 1]) > maxw)
            out.append((start, end))
            start = end + (text[end:end + 1] == " ")
        pos += len(para) + 1
    return out


def render(row):
    """-> (image, labels). label = {text, label, box}; a span split across lines gives one label per piece."""
    mono = row["document_format"] == "structured"
    font = ImageFont.truetype(MONO if mono else SANS, SIZE)
    text = row["text"].replace("\t", "    ")
    lines = wrap(text, font, W - 2 * MARGIN)[:MAX_LINES]
    img = Image.new("RGB", (W, 2 * MARGIN + LEADING * len(lines)), "white")
    d = ImageDraw.Draw(img)
    labels = []
    for n, (s, e) in enumerate(lines):
        y = MARGIN + n * LEADING
        d.text((MARGIN, y), text[s:e], font=font, fill="#1f2328")
        for sp in row["spans"]:
            a, b = max(sp["start"], s), min(sp["end"], e)
            if a >= b or not text[a:b].strip():
                continue
            x0 = MARGIN + font.getlength(text[s:a])
            box = d.textbbox((x0, y), text[a:b], font=font)
            labels.append({"text": text[a:b], "label": sp["label"], "box": list(box)})
    return img, labels


def score(results):
    tot = caught = drawn = good = leaks = 0
    for labels, boxes in results:
        need = [l for l in labels if l.get("sensitive") or l.get("label") in SENSITIVE]
        miss = [l for l in need if not covered(l["box"], boxes)]
        tot += len(need); caught += len(need) - len(miss); leaks += bool(miss)
        drawn += len(boxes); good += sum(any(overlaps(b, l["box"]) for l in labels) for b in boxes)
    return caught / max(tot, 1), good / max(drawn, 1), leaks, len(results), caught, tot


def nemotron_docs(n, seed, save):
    rows = pq.read_table(DATA, columns=["uid", "document_format", "text", "spans"]).to_pylist()
    rng = random.Random(seed)
    pick = []
    for fmt in ("structured", "unstructured"):
        pick += rng.sample([r for r in rows if r["document_format"] == fmt], n // 2)
    docs = []
    for r in pick:
        r["spans"] = ast.literal_eval(r["spans"])
        img, labels = render(r)
        docs.append((r["document_format"], img, labels))
        if save:
            img.save(Path(save) / f"{r['document_format'][:5]}_{r['uid'][:8]}.png")
    return docs


def ui_docs(n, split, save):
    docs = []
    for s in range(1000 if split == "test" else 0, (1000 if split == "test" else 0) + n):
        img, labels, layout = uiset.make(s)
        docs.append((layout, img, [{**l, "sensitive": True} for l in labels]))
        if save:
            img.save(Path(save) / f"{s}_{layout}.png")
    return docs


def detect(det, img):
    return maskly.detect(img, use_gemma=det != "rules")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["ui", "nemotron"], default="ui")
    ap.add_argument("--split", choices=["tune", "test"], default="tune", help="ui only")
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--detectors", default="rules")
    ap.add_argument("--gemma-n", type=int, default=6, help="Gemma is slow; score it on the first N docs per group")
    ap.add_argument("--seed", type=int, default=1, help="nemotron sampling seed")
    ap.add_argument("--save", help="folder to write rendered PNGs for a look")
    a = ap.parse_args()
    if a.save:
        Path(a.save).mkdir(exist_ok=True)
    docs = ui_docs(a.n, a.split, a.save) if a.set == "ui" else nemotron_docs(a.n, a.seed, a.save)
    groups = sorted({g for g, *_ in docs})
    print(f"{a.set}/{a.split if a.set == 'ui' else a.seed}: {len(docs)} docs, {sum(len(l) for *_, l in docs)} labels")
    for det in a.detectors.split(","):
        sub = [d for g in groups for d in [x for x in docs if x[0] == g][:a.gemma_n]] if det == "gemma" else docs
        res, ms = {g: [] for g in groups}, []
        for g, img, labels in sub:
            t = time.perf_counter()
            r = detect(det, img)
            ms.append((time.perf_counter() - t) * 1000)
            if r["partial"]:
                print(f"  {det} partial: {r['error']}")
            res[g].append((labels, [b["box"] for b in r["boxes"]]))
        print(f"\n{det.upper()}  (median {sorted(ms)[len(ms) // 2]:.0f} ms/doc incl. OCR)")
        for g in groups + ["ALL"]:
            rows = [x for k in groups for x in res[k]] if g == "ALL" else res[g]
            if rows:
                rc, pr, lk, n, c, t = score(rows)
                print(f"  {g:12} recall {c}/{t} = {rc:.0%} · precision {pr:.0%} · leaky {lk}/{n} = {lk / n:.0%}")


if __name__ == "__main__":
    main()
