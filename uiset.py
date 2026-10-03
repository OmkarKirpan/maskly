"""UI-style benchmark screenshots: five support-tool layouts with labelled sensitive values and decoys.
make(seed) -> (image, labels, layout). Seeds 0-999 are for tuning, 1000+ for the ship gate (bench.py).
Values mix Faker (en_IN / en_US / en_GB) with Nemotron-PII train-split values when data/ has them.
Preview: uv run python uiset.py OUT_DIR [first_seed] [count]"""
import ast
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

from faker import Faker
from PIL import Image, ImageDraw, ImageFont

from samples import aadhaar, card, pan

TRAIN = Path(__file__).parent / "data" / "nemotron-pii-train.parquet"
FONTS = {
    "sans": ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/calibri.ttf",
             "C:/Windows/Fonts/tahoma.ttf", "C:/Windows/Fonts/verdana.ttf", "/System/Library/Fonts/Helvetica.ttc",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    "mono": ["C:/Windows/Fonts/consola.ttf", "C:/Windows/Fonts/cour.ttf", "/System/Library/Fonts/Menlo.ttc",
             "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"],
}
FONTS = {k: [f for f in v if Path(f).exists()] for k, v in FONTS.items()}
THEMES = [
    {"bg": "#f6f8fa", "panel": "#ffffff", "fg": "#1f2328", "muted": "#57606a", "accent": "#0969da", "border": "#d0d7de"},
    {"bg": "#0d1117", "panel": "#161b22", "fg": "#e6edf3", "muted": "#8b949e", "accent": "#2f81f7", "border": "#30363d"},
]

# ---------------------------------------------------------------- values

_pool = None


def _nemotron():
    """label -> list of real-looking values from the Nemotron train split (empty if not downloaded)."""
    global _pool
    if _pool is None:
        _pool = {}
        if TRAIN.exists():
            import pyarrow.parquet as pq
            keep = {"first_name", "last_name", "customer_id", "account_number", "employee_id", "user_name",
                    "street_address", "api_key", "password", "phone_number", "medical_record_number"}
            for r in pq.read_table(TRAIN, columns=["spans"]).slice(0, 20000).to_pylist():
                for s in ast.literal_eval(r["spans"]):
                    t = str(s["text"]).strip()
                    if s["label"] in keep and 2 <= len(t) <= 40 and "\n" not in t \
                            and not (s["label"] == "password" and " " in t):
                        _pool.setdefault(s["label"], []).append(t)
    return _pool


class Values:
    """Random sensitive values by Maskly category, plus decoys that look data-like but are not personal."""

    def __init__(self, rng):
        self.r = rng
        self.locale = rng.choice(["en_IN", "en_US", "en_GB"])
        self.f = Faker(self.locale)
        self.f.seed_instance(rng.randrange(1 << 30))
        self.pool = _nemotron()

    def _p(self, label, fallback):
        vals = self.pool.get(label)
        return self.r.choice(vals) if vals and self.r.random() < 0.6 else fallback()

    def get(self, cat):
        r, f = self.r, self.f
        return {
            "person_name": lambda: f"{self._p('first_name', f.first_name)} {self._p('last_name', f.last_name)}",
            "email": f.email,
            "phone": lambda: self._p("phone_number", f.phone_number),
            "postal_address": lambda: f"{self._p('street_address', f.street_address)}, {f.city()}"
                                      + (f" {f.postcode()}" if r.random() < 0.5 else ""),
            "customer_or_order_id": lambda: r.choice([
                lambda: self._p("customer_id", lambda: f"CUS{r.randint(10**5, 10**6 - 1)}"),
                lambda: f"ORD-{r.randint(10**5, 10**6 - 1)}",
                lambda: f"INV-2026-{r.randint(10**4, 10**5 - 1)}",
                lambda: f"#{r.randint(10**4, 10**5 - 1)}",
                lambda: self._p("employee_id", lambda: f"EMP{r.randint(1000, 9999)}"),
                lambda: self._p("medical_record_number", lambda: f"MRN-{r.randint(10**5, 10**6 - 1)}"),
            ])(),
            "username": lambda: self._p("user_name", f.user_name),
            "bank_details": lambda: r.choice([
                lambda: self._p("account_number", lambda: str(r.randint(10**10, 10**12))),
                lambda: "HDFC0" + str(r.randint(10**5, 10**6 - 1)),
                f.iban,
            ])(),
            "card": lambda: card(r),
            "national_id": lambda: {"en_IN": lambda: r.choice([aadhaar, pan])(r), "en_US": f.ssn,
                                    "en_GB": lambda: f.ssn()}[self.locale](),
            "ip_address": f.ipv4_public,
            "mac_address": f.mac_address,
            "internal_url": lambda: f"{r.choice(['pay', 'auth', 'orders', 'crm'])}-{r.choice(['db', 'api', 'cache'])}"
                                    f"-{r.randint(1, 9)}.{r.choice(['prod', 'stg'])}.{r.choice(['internal', 'corp'])}",
            "secret": lambda: r.choice([
                lambda: self._p("api_key", lambda: "sk-" + f.pystr(min_chars=32, max_chars=32)),
                lambda: "ghp_" + "".join(r.choices("abcdefghijklmnopqrstuvwxyzABCDEF0123456789", k=36)),
                lambda: "AKIA" + "".join(r.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567", k=16)),
            ])(),
            "password": lambda: self._p("password", lambda: f.password(length=12)),
            "date_of_birth": lambda: f.date_of_birth(minimum_age=18, maximum_age=80).strftime(
                r.choice(["%d/%m/%Y", "%Y-%m-%d", "%b %d, %Y"])),
        }[cat]()

    def decoy(self, kind=None):
        r = self.r
        ts = datetime(2026, 9, 1) + timedelta(seconds=r.randrange(60 * 86400))
        return {
            "status": lambda: r.choice(["Open", "Escalated to billing", "Resolved", "Pending documents",
                                        "Waiting on customer", "Refund initiated"]),
            "amount": lambda: r.choice(["₹", "$", "£"]) + f"{r.randint(1, 9999):,}.{r.randint(0, 99):02d}",
            "version": lambda: f"v{r.randint(1, 4)}.{r.randint(0, 20)}.{r.randint(0, 9)}",
            "time": lambda: ts.strftime(r.choice(["%Y-%m-%d %H:%M", "%d %b %Y, %I:%M %p", "%H:%M:%S"])),
            "hash": lambda: "".join(r.choices("0123456789abcdef", k=r.choice([7, 12]))),
            "product": lambda: r.choice(["Wireless Mouse M185", "Premium plan (annual)", "USB-C Hub 7-in-1",
                                         "Gift card", "Pro subscription", "Noise-cancelling headphones"]),
            "priority": lambda: r.choice(["Low", "Medium", "High", "Urgent"]),
            "channel": lambda: r.choice(["Email", "Chat", "Phone", "WhatsApp"]),
            "count": lambda: str(r.randint(1, 12)),
        }[kind or r.choice(["status", "amount", "version", "time", "hash", "product", "priority"])]()


LABELS = {  # category -> field labels a support tool might show
    "person_name": ["Customer", "Name", "Account holder", "Full name", "Requester", "Contact"],
    "email": ["Email", "Email address", "Contact email", "E-mail"],
    "phone": ["Phone", "Mobile", "Phone number", "Contact no."],
    "postal_address": ["Address", "Shipping address", "Billing address", "Delivery address"],
    "customer_or_order_id": ["Order #", "Order ID", "Customer ID", "Ticket", "Invoice", "Reference"],
    "username": ["Username", "Login", "User"],
    "bank_details": ["Account no.", "Bank account", "IBAN", "IFSC / Account"],
    "card": ["Card", "Card number", "Payment card"],
    "national_id": ["National ID", "ID number", "Tax ID", "SSN / Aadhaar / PAN"],
    "ip_address": ["Client IP", "IP address", "Last IP"],
    "mac_address": ["Device MAC", "MAC address"],
    "internal_url": ["Host", "Server", "Database host"],
    "secret": ["API key", "Token", "Access key"],
    "password": ["Temp password", "Password"],
    "date_of_birth": ["Date of birth", "DOB"],
}
DECOY_LABELS = {"status": ["Status", "State"], "amount": ["Amount", "Order total", "Refund"],
                "version": ["App version", "Build"], "time": ["Created", "Last updated", "Last login"],
                "hash": ["Commit", "Request ID"], "product": ["Product", "Plan", "Item"],
                "priority": ["Priority", "Severity"], "channel": ["Channel", "Source"]}

# ---------------------------------------------------------------- drawing


def _text(words):
    return " ".join("".join(ch for ch, _ in w) for w in words)


class Canvas:
    def __init__(self, w, theme, font_path, size, mono_path):
        self.img = Image.new("RGB", (w, 2400), theme["bg"])
        self.d = ImageDraw.Draw(self.img)
        self.t, self.w, self.size, self.labels = theme, w, size, []
        self.font = ImageFont.truetype(font_path, size)
        self.small = ImageFont.truetype(font_path, max(12, size - 4))
        self.big = ImageFont.truetype(font_path, size + 8)
        self.mono = ImageFont.truetype(mono_path, size - 2)
        self.lh = int(size * 1.6)

    def text(self, xy, parts, font=None, fill=None):
        """Draw [(text, category or None), ...] left to right; label every part that has a category."""
        font = font or self.font
        if isinstance(parts, str):
            parts = [(parts, None)]
        x, y = xy
        for txt, cat in parts:
            self.d.text((x, y), txt, font=font, fill=fill or self.t["fg"])
            if cat:
                self.labels.append({"text": txt, "category": cat, "box": list(self.d.textbbox((x, y), txt, font=font))})
            x += font.getlength(txt)
        return x

    def para(self, x, y, parts, maxw, font=None, fill=None):
        """Word-wrap labelled parts into maxw; returns the y below the last line."""
        font = font or self.font
        # Words are lists of (char, category); a space inside one value keeps that value's category.
        words, cur = [], []
        for txt, cat in parts:
            for ch in txt:
                if ch == " ":
                    if cur:
                        words.append(cur)
                    cur = []
                else:
                    cur.append((ch, cat))
        if cur:
            words.append(cur)
        lines, line = [], []
        for w in words:
            if line and font.getlength(_text(line + [w])) > maxw:
                lines.append(line)
                line = []
            line.append(w)
        lines.append(line)
        for line in lines:
            chars = []
            for i, w in enumerate(line):
                if i:
                    same = line[i - 1][-1][1] == w[0][1]
                    chars.append((" ", w[0][1] if same else None))
                chars += w
            parts = []
            for ch, cat in chars:
                if parts and parts[-1][1] == cat:
                    parts[-1] = (parts[-1][0] + ch, cat)
                else:
                    parts.append((ch, cat))
            self.text((x, y), parts, font, fill)
            y += self.lh
        return y

    def button(self, x, y, label):
        w = self.small.getlength(label) + 24
        self.d.rounded_rectangle([x, y, x + w, y + self.lh], 6, outline=self.t["border"], fill=self.t["panel"])
        self.text((x + 12, y + (self.lh - self.size + 4) / 2), label, self.small, self.t["accent"])
        return x + w + 12

    def done(self, bottom):
        return self.img.crop((0, 0, self.w, int(bottom) + 40))


def _fields(v, r, n_sensitive, n_decoy, cats=None):
    cats = cats or list(LABELS)
    out = [(r.choice(LABELS[c]), [(v.get(c), c)]) for c in r.sample(cats, n_sensitive)]
    out += [(r.choice(DECOY_LABELS[k]), [(v.decoy(k), None)]) for k in r.sample(list(DECOY_LABELS), n_decoy)]
    r.shuffle(out)
    return out


def ticket(c, v, r):
    c.d.rectangle([0, 0, c.w, 70], fill=c.t["panel"])
    tid = v.get("customer_or_order_id")
    c.text((30, 20), [("Support Desk - Ticket ", None), (tid, "customer_or_order_id")], c.big)
    col = 60 + max(c.font.getlength(x) for xs in LABELS.values() for x in xs) + 40
    y = 110
    for label, value in _fields(v, r, r.randint(5, 8), r.randint(2, 4)):
        c.text((60, y), label, c.font, c.t["muted"])
        c.text((col, y), value)
        y += c.lh + 12
    x = 60
    for b in r.sample(["Reply", "Escalate", "Close ticket", "Add note", "Merge"], 3):
        x = c.button(x, y + 10, b)
    return y + c.lh + 20


def table(c, v, r):
    cols = [("Customer", "person_name"), ("Email", "email"), ("Phone", "phone"), ("Order", "customer_or_order_id"),
            ("Card", "card"), ("Amount", "amount"), ("Status", "status"), ("Created", "time"), ("City", None)]
    cols = [cols[0]] + r.sample(cols[1:], r.randint(3, 5))
    rows = [[(v.get(k), k) if k in LABELS else (v.decoy(k), None) if k else (v.f.city(), None) for _, k in cols]
            for _ in range(r.randint(5, 9))]
    widths = [max([c.font.getlength(h)] + [c.font.getlength(row[i][0]) for row in rows]) + 40 for i, (h, _) in enumerate(cols)]
    while sum(widths) + 80 > c.w and len(cols) > 3:  # drop columns that do not fit
        cols, widths, rows = cols[:-1], widths[:-1], [row[:-1] for row in rows]
    c.text((40, 24), r.choice(["Customers", "Recent orders", "Refund queue", "Escalations"]), c.big)
    y = 90
    x = 40
    for (h, _), w in zip(cols, widths):
        c.text((x, y), h, c.font, c.t["muted"])
        x += w
    y += c.lh + 8
    for row in rows:
        c.d.line([40, y - 6, 40 + sum(widths), y - 6], fill=c.t["border"])
        x = 40
        for part, w in zip(row, widths):
            c.text((x, y), [part])
            x += w
        y += c.lh + 8
    return y


CUSTOMER = [
    "Hi, this is {person_name}. My order {customer_or_order_id} still hasn't arrived.",
    "You can reach me on {phone} or at {email}.",
    "Please ship the replacement to {postal_address}.",
    "I was charged twice on my card {card}, please check.",
    "Refund it to account {bank_details} please.",
    "My username is {username} and I can't log in since yesterday.",
    "I already shared my ID {national_id} with your team.",
    "Is there any update? It has been {count} days now.",
    "Thanks, that works for me.",
]
AGENT = [
    "Thanks for reaching out! I can see order {customer_or_order_id} was delayed at the hub.",
    "I've escalated this to billing. Your reference is {customer_or_order_id}.",
    "A refund of {amount} will reach you in 5-7 working days.",
    "Could you confirm the email on the account?",
    "I've reset your password. Your temporary password is {password}.",
    "Sorry for the trouble. Is there anything else I can help with?",
]


def _fill(tpl, v):
    parts, rest = [], tpl
    while "{" in rest:
        pre, rest = rest.split("{", 1)
        key, rest = rest.split("}", 1)
        parts.append((pre, None))
        parts.append((v.get(key), key) if key in LABELS else (v.decoy(key), None))
    parts.append((rest, None))
    return [p for p in parts if p[0]]


def chat(c, v, r):
    name = v.get("person_name")
    c.text((40, 24), [("Chat with ", None), (name, "person_name")], c.big)
    y, maxw = 100, min(900, c.w - 200)
    for i in range(r.randint(4, 7)):
        mine = i % 2 == 0
        tpl = r.choice(CUSTOMER if mine else AGENT)
        x = 40 if mine else c.w - maxw - 80
        who = [(name.split()[0], "person_name")] if mine else [(r.choice(["Support Agent", "Billing Team", "Helpdesk Bot"]), None)]
        c.text((x + 16, y), who + [(f"  {v.decoy('time')}", None)], c.small, c.t["muted"])
        y += c.lh
        top = y
        y = c.para(x + 16, y + 8, _fill(tpl, v), maxw - 32)
        c.d.rounded_rectangle([x, top, x + maxw, y + 8], 10, outline=c.t["border"])
        y += 28
    return y


LOG = [
    "{time} INFO  {svc} request_id={hash} user={email} ip={ip_address} latency={count}ms",
    "{time} ERROR {svc} charge failed order={customer_or_order_id} card={card} msg=\"Timeout while charging card\"",
    "{time} WARN  {svc} login retry user={username} from {ip_address}",
    "{time} DEBUG {svc} Authorization: Bearer {secret}",
    "{time} INFO  {svc} db host={internal_url} pool={count} ok",
    "{time} INFO  {svc} healthcheck ok version={version}",
    "{time} ERROR {svc} device {mac_address} offline",
    "{time} INFO  {svc} webhook delivered id={hash} status=200",
]


def log(c, v, r):
    c.text((30, 20), [("Error details - ", None), (v.decoy("hash"), None)], c.big)
    y = 80
    for _ in range(r.randint(10, 16)):
        tpl = r.choice(LOG).replace("{svc}", r.choice(["payments-api", "auth", "orders", "notify"]))
        y = c.para(30, y, _fill(tpl, v), c.w - 60, c.mono)
    return y


def profile(c, v, r):
    name = v.get("person_name")
    c.d.ellipse([60, 40, 160, 140], fill=c.t["accent"])
    c.text((190, 60), [(name, "person_name")], c.big)
    c.text((190, 60 + c.lh + 8), [(v.decoy("product"), None), ("  ·  Member since 2021", None)], c.small, c.t["muted"])
    fields = _fields(v, r, r.randint(5, 8), r.randint(2, 3), [k for k in LABELS if k != "person_name"])
    colw, y0 = (c.w - 120) // 2, 200
    for i, (label, value) in enumerate(fields):
        x, y = 60 + (i % 2) * colw, y0 + (i // 2) * (2 * c.lh + 20)
        c.text((x, y), label, c.small, c.t["muted"])
        c.text((x, y + c.lh), value)
    return y0 + ((len(fields) + 1) // 2) * (2 * c.lh + 20)


LAYOUTS = [ticket, table, chat, log, profile]


def make(seed):
    r = random.Random(seed)
    layout = LAYOUTS[seed % len(LAYOUTS)]
    c = Canvas(r.choice([1280, 1440, 1600, 1920]), r.choice(THEMES), r.choice(FONTS["sans"]),
               r.randint(14, 24), r.choice(FONTS["mono"]))
    bottom = layout(c, Values(r), r)
    return c.done(bottom), c.labels, layout.__name__


if __name__ == "__main__":
    out = Path(sys.argv[1])
    out.mkdir(exist_ok=True)
    start, count = (int(sys.argv[2]) if len(sys.argv) > 2 else 0), (int(sys.argv[3]) if len(sys.argv) > 3 else 5)
    for s in range(start, start + count):
        img, labels, name = make(s)
        img.save(out / f"{s}_{name}.png")
        print(s, name, img.size, len(labels), "labels")
