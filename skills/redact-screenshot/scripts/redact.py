# /// script
# requires-python = ">=3.12"
# dependencies = ["maskly @ git+https://github.com/OmkarKirpan/maskly"]
# ///
"""Redact personal data in a screenshot. Usage: uv run scripts/redact.py <image> [-o out.png] [--rules-only] [--allow-cloud] | --fetch-model
Prints a JSON report (counts only, never the redacted text). Exit 0 = full scan, 2 = partial scan, 1 = error."""
import sys

from maskly import cli

sys.exit(cli())
