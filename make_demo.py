"""Save real pipeline results for samples/*.png into demo/ for the GitHub Pages demo.
Run: uv run --env-file .env python make_demo.py"""
import json
from pathlib import Path

from PIL import Image

import maskly

ROOT = Path(__file__).parent
(ROOT / "demo").mkdir(exist_ok=True)
for png in sorted((ROOT / "samples").glob("*.png")):
    r = maskly.detect(Image.open(png).convert("RGB"))
    (ROOT / "demo" / f"{png.stem}.json").write_text(json.dumps(r))
    print(png.stem, r["backend"], len(r["boxes"]), "boxes", r["ms"])
