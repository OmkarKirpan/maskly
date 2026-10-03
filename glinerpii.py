"""GLiNER-PII detector: a 184M span model (knowledgator/gliner-pii-small-v1.0, Apache-2.0, ONNX quint8, 83 MB)
that marks the personal words inside each OCR line in one pass. Runs on onnxruntime + tokenizers, no PyTorch.

Each OCR line is read with its row label as context ("Customer: Matthew Rana"), so a UI value gets the field
name it sits next to, and a chat or log line gets only its own words boxed. Prompt layout and start/end/inside
decoding follow GLiNER's token-level processor and decoder (github.com/urchade/GLiNER)."""
import hashlib
import os
import re
from pathlib import Path

import numpy as np

from maskly import is_label, row_left

MODEL_DIR = Path(os.environ.get("MASKLY_GLINER_DIR", Path.home() / ".cache" / "maskly" / "gliner-pii-small"))
REPO, REVISION = "knowledgator/gliner-pii-small-v1.0", "d21aad5b4a7ec82b3d0970fd1ac74a12c087d85e"
FILES = {  # local name -> (path in repo, sha256), pinned to REVISION
    "model_quint8.onnx": ("onnx/model_quint8.onnx", "891589426ee96f2748b16439f44fad8c3f97e198e002a6637e58dee989500216"),
    "tokenizer.json": ("tokenizer.json", "84b3a9b18f04a0ccd03b72d9f871b7e0bec40fd7021ef50bc30a7c3693c11205"),
}
BATCH = 16
SPLIT = re.compile(r"\w+(?:[-_]\w+)*|\S")  # GLiNER's whitespace splitter
LABELS = {  # prompt label -> Maskly category
    "person name": "person_name",
    "email address": "email",
    "phone number": "phone",
    "street address": "postal_address",
    "postal code": "postal_address",
    "order id": "customer_or_order_id",
    "customer id": "customer_or_order_id",
    "ticket id": "customer_or_order_id",
    "username": "other_personal",
    "ip address": "ip_address",
    "mac address": "mac_address",
    "national id": "national_id",
    "bank account number": "bank_details",
    "credit card number": "card",
    "password": "secret",
    "api key": "secret",
    "hostname": "internal_url",
    "date of birth": "date_of_birth",
}

_s = None  # (session, tokenizer)


def _sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(progress=print):
    """Download the pinned model files into MODEL_DIR and check every sha256. Safe to re-run."""
    import httpx
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for name, (path, sha) in FILES.items():
        dest = MODEL_DIR / name
        if dest.exists() and _sha256(dest) == sha:
            continue
        tmp = dest.with_suffix(dest.suffix + ".part")
        progress(f"downloading {path}")
        with httpx.stream("GET", f"https://huggingface.co/{REPO}/resolve/{REVISION}/{path}",
                          follow_redirects=True, timeout=60) as r, open(tmp, "wb") as f:
            r.raise_for_status()
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
        if _sha256(tmp) != sha:
            tmp.unlink()
            raise ValueError(f"{path}: sha256 mismatch, download rejected")
        tmp.replace(dest)
    progress(f"GLiNER-PII model ready in {MODEL_DIR}")


def available():
    return all((MODEL_DIR / n).exists() for n in FILES)


def _load():
    global _s
    if _s is None:
        import onnxruntime as ort
        from tokenizers import Tokenizer
        if not available():
            raise FileNotFoundError(f"GLiNER-PII model not found in {MODEL_DIR}: run `uv run maskly --fetch-model`")
        _s = (ort.InferenceSession(str(MODEL_DIR / "model_quint8.onnx"), providers=["CPUExecutionProvider"]),
              Tokenizer.from_file(str(MODEL_DIR / "tokenizer.json")))
    return _s


def spans(texts, threshold):
    """texts -> per text a list of (char_start, char_end, category, score), non-overlapping."""
    sess, tok = _load()
    labels = list(LABELS)
    prompt = [t for lab in labels for t in ("<<ENT>>", lab)] + ["<<SEP>>"]
    out = []
    for b in range(0, len(texts), BATCH):
        chunk = texts[b:b + BATCH]
        words = [[(m.start(), m.end()) for m in SPLIT.finditer(t)] for t in chunk]
        encs, masks = [], []
        for t, ws in zip(chunk, words):
            enc = tok.encode(prompt + [t[s:e] for s, e in ws], is_pretokenized=True)
            mask, prev = [], None
            for wid in enc.word_ids:  # 1-based index on the first subtoken of each text word, else 0
                mask.append(wid - len(prompt) + 1 if wid is not None and wid >= len(prompt) and wid != prev else 0)
                prev = wid
            encs.append(enc.ids)
            masks.append(mask)
        L = max(len(e) for e in encs)
        pad = lambda rows, v: np.array([r + [v] * (L - len(r)) for r in rows], dtype=np.int64)
        logits = sess.run(None, {
            "input_ids": pad(encs, tok.token_to_id("[PAD]")),
            "attention_mask": pad([[1] * len(e) for e in encs], 0),
            "words_mask": pad(masks, 0),
            "text_lengths": np.array([[len(ws)] for ws in words], dtype=np.int64),
        })[0]
        p = 1 / (1 + np.exp(-logits))  # (B, words, labels, start/end/inside)
        for i, ws in enumerate(words):
            cand = []
            for c in range(len(labels)):
                pc = p[i, :len(ws), c]
                ends = np.where(pc[:, 1] > threshold)[0]
                for st in np.where(pc[:, 0] > threshold)[0]:
                    for ed in ends[ends >= st]:
                        inside = pc[st:ed + 1, 2]
                        if (inside >= threshold).all():
                            cand.append((float(min(inside.min(), pc[st, 0], pc[ed, 1])), st, ed, c))
            keep = []  # greedy: best score first, no overlaps (GLiNER flat_ner)
            for sc, st, ed, c in sorted(cand, reverse=True):
                if all(ed < k[1] or st > k[2] for k in keep):
                    keep.append((sc, st, ed, c))
            out.append([(ws[st][0], ws[ed][1], LABELS[labels[c]], sc) for sc, st, ed, c in keep])
    return out


def findings(words, lines, skip, threshold):
    """Same shape as maskly.gemma(): one finding per detected span, mapped back to the OCR words it covers."""
    texts, offsets, todo = [], [], []
    for n, ids in enumerate(lines):
        if all(i in skip for i in ids) or is_label(" ".join(words[i]["text"] for i in ids)):
            continue  # a field name such as "IP address" scores as the data it names
        left = row_left(words, lines, n)
        prefix = " ".join(words[i]["text"] for i in lines[left]) + ": " if left is not None else ""
        text, offs = prefix, []
        for i in ids:
            if text != prefix:
                text += " "
            offs.append((len(text), len(text) + len(words[i]["text"]), i))
            text += words[i]["text"]
        texts.append(text)
        offsets.append(offs)
        todo.append(n)
    out = []
    for text, offs, found in zip(texts, offsets, spans(texts, threshold)):
        for s, e, cat, sc in found:
            if cat == "date_of_birth" and not re.search(r"(?i)birth|\bdob\b|\bborn\b", text):
                continue  # any timestamp scores as a birth date; keep it only where the screen says so
            ids = [i for a, b, i in offs if a < e and s < b and i not in skip]
            if ids:  # spans inside the row-label prefix map to no word and are dropped
                out.append({"word_ids": ids, "category": cat, "confidence": round(sc, 2), "reason": f"GLiNER: {cat}"})
    return out
