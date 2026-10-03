"""Recall/precision on samples/: rules only vs rules + model (GLiNER, or Gemma if GLiNER is not fetched). Run: uv run python eval.py [--no-gemma]"""
import json
import sys
from pathlib import Path

from PIL import Image

import maskly

PAD = 4  # same padding the UI uses


def covered(label, boxes):
    """A label counts as caught when padded boxes cover >= 90% of its pixels."""
    x0, y0, x1, y1 = label
    hit = 0
    for x in range(int(x0), int(x1)):
        for y in range(int(y0), int(y1)):
            hit += any(b[0] - PAD <= x <= b[2] + PAD and b[1] - PAD <= y <= b[3] + PAD for b in boxes)
    return hit >= 0.9 * max(1, (int(x1) - int(x0)) * (int(y1) - int(y0)))


def overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def run(use_model):
    tot = caught = drawn = good = leaks = 0
    for png in sorted(Path(__file__).parent.glob("samples/*.png")):
        labels = json.loads(png.with_suffix(".json").read_text())
        r = maskly.detect(Image.open(png).convert("RGB"), use_model=use_model)
        boxes = [b["box"] for b in r["boxes"]]
        miss = [l["text"] for l in labels if not covered(l["box"], boxes)]
        tot += len(labels); caught += len(labels) - len(miss); leaks += bool(miss)
        drawn += len(boxes); good += sum(any(overlaps(b, l["box"]) for l in labels) for b in boxes)
        print(f"  {png.stem}: {len(labels) - len(miss)}/{len(labels)} caught, {r['ms']}, partial={r['partial']} backend={r['backend']}"
              + (f" missed={miss}" if miss else ""))
    print(f"recall {caught}/{tot} = {caught / max(tot, 1):.0%} · precision {good}/{drawn} = {good / max(drawn, 1):.0%}"
          f" · leaky screenshots {leaks}")


if __name__ == "__main__":
    print("RULES ONLY"); run(False)
    if "--no-gemma" not in sys.argv:
        print("RULES + MODEL"); run(True)
