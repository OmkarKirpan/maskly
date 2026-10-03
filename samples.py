"""Make fake support screenshots + labels. Run: uv run python samples.py  (writes samples/*.png, *.json)"""
import json
import random
from pathlib import Path

from faker import Faker
from PIL import Image, ImageDraw, ImageFont

from maskly import luhn, verhoeff_digit

fk = Faker("en_IN")
Faker.seed(7)
random.seed(7)
OUT = Path(__file__).parent / "samples"
FONT = next(f for f in ["/System/Library/Fonts/Helvetica.ttc", "C:/Windows/Fonts/arial.ttf",
                         "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"] if Path(f).exists())


def card(rng=random):
    while True:
        n = "4" + "".join(rng.choices("0123456789", k=15))
        if luhn(n):
            return " ".join(n[i:i + 4] for i in range(0, 16, 4))


def aadhaar(rng=random):
    n = str(rng.randint(2, 9)) + "".join(rng.choices("0123456789", k=10))
    n += verhoeff_digit(n)
    return f"{n[:4]} {n[4:8]} {n[8:]}"


def pan(rng=random):
    return "".join(rng.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=5)) + str(rng.randint(1000, 9999)) + rng.choice("ABCDEFGHJK")


def render(name, rows, title):
    """rows: list of (label, value, category or None). Sensitive values are labelled with their pixel box."""
    img = Image.new("RGB", (1920, 1080), "#f4f6f8")
    d = ImageDraw.Draw(img)
    f, fb, ft = (ImageFont.truetype(FONT, s) for s in (24, 24, 34))
    d.rectangle([0, 0, 1920, 70], fill="#1f3a5f")
    d.text((30, 18), title, font=ft, fill="white")
    d.rectangle([60, 110, 1860, 130 + 58 * len(rows)], fill="white", outline="#d0d7de")
    labels, y = [], 130
    for label, value, cat in rows:
        d.text((90, y), label, font=fb, fill="#57606a")
        d.text((420, y), value, font=f, fill="#1f2328")
        if cat:
            labels.append({"text": value, "category": cat, "box": list(d.textbbox((420, y), value, font=f))})
        y += 58
    OUT.mkdir(exist_ok=True)
    img.save(OUT / f"{name}.png")
    (OUT / f"{name}.json").write_text(json.dumps(labels, indent=1))


def main():
    p = fk.name()
    render("dashboard", [
        ("Ticket", f"#{random.randint(10000, 99999)} - Refund not received", None),
        ("Customer", p, "person_name"),
        ("Email", fk.email(), "email"),
        ("Phone", "+91 " + fk.msisdn()[3:8] + " " + fk.msisdn()[8:13], "phone"),
        ("Order #", f"ORD-{random.randint(100000, 999999)}", "customer_or_order_id"),
        ("Card", card(), "card"),
        ("Address", fk.street_address() + ", " + fk.city(), "postal_address"),
        ("Status", "Escalated to billing team", None),
        ("Priority", "High", None),
    ], "Support Desk - Ticket view")
    render("kyc", [
        ("Account holder", fk.name(), "person_name"),
        ("Aadhaar", aadhaar(), "aadhaar"),
        ("PAN", pan(), "pan"),
        ("IFSC", "HDFC0" + str(random.randint(100000, 999999)), "bank_details"),
        ("Account no.", str(random.randint(10**11, 10**12 - 1)), "bank_details"),
        ("Verified by", "Support agent", None),
        ("KYC status", "Pending documents", None),
    ], "KYC Review")
    render("errorlog", [
        ("Time", "2026-10-03 11:42:07 UTC", None),
        ("Service", "payments-api", None),
        ("Host", "pay-db-2.prod.internal", "internal_url"),
        ("Client IP", fk.ipv4_public(), "ip_address"),
        ("User", fk.email(), "email"),
        ("Token", "ghp_" + "".join(random.choices("abcdefghijklmnopqrstuvwxyzABCDEF0123456789", k=36)), "secret"),
        ("Error", "Timeout while charging card", None),
    ], "Error details")
    print("wrote", sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
