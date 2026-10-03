"""Windows desktop shell. Run: uv run --extra desktop maskly-desktop"""
import base64
import ctypes
import io
import os
import socket
import threading
import time
from ctypes import wintypes

import uvicorn
import webview
from PIL import Image, ImageGrab

import app

user32 = ctypes.windll.user32
MODS = {"alt": 0x1, "ctrl": 0x2, "shift": 0x4, "win": 0x8}
MOD_NOREPEAT, WM_HOTKEY, WM_QUIT = 0x4000, 0x0312, 0x0012


class Api:
    # Exposed to the page over the pywebview bridge, not HTTP: any local web page could call a route.
    def clipboard_png(self) -> str | None:
        clip = ImageGrab.grabclipboard()
        if isinstance(clip, list):
            ok = len(clip) == 1 and clip[0].lower().endswith((".png", ".jpg", ".jpeg"))
            clip = Image.open(clip[0]) if ok else None
        if not isinstance(clip, Image.Image):
            return None
        buf = io.BytesIO()
        clip.save(buf, "PNG")
        return base64.b64encode(buf.getvalue()).decode()


def serve() -> str:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(app.app, log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    while not server.started:
        if not thread.is_alive():
            raise SystemExit("Maskly server failed to start")
        time.sleep(0.05)
    return f"http://127.0.0.1:{sock.getsockname()[1]}/"


def parse_hotkey(spec: str) -> tuple[int, int]:
    *mods, key = spec.lower().split("+")
    if len(key) != 1 or not key.isalnum() or not set(mods) <= MODS.keys():
        raise SystemExit(f"MASKLY_HOTKEY={spec!r}: use ctrl/alt/shift/win plus one letter or digit, like ctrl+alt+m")
    return sum(MODS[m] for m in set(mods)) | MOD_NOREPEAT, ord(key.upper())


def summon(window: webview.Window) -> None:
    from System import Action  # pythonnet, already loaded by pywebview's WinForms backend
    from System.Windows.Forms import FormWindowState

    form = window.native

    def front():
        if form.WindowState == FormWindowState.Minimized:
            form.WindowState = FormWindowState.Normal
        form.Show()
        form.Activate()  # the hotkey press grants this process foreground rights

    form.Invoke(Action(front))
    window.evaluate_js("scanClipboard()")


def listen(spec: str, mods: int, vk: int, window: webview.Window) -> None:
    # RegisterHotKey(NULL) posts WM_HOTKEY to the registering thread, so register and pump here.
    if not user32.RegisterHotKey(None, 1, mods, vk):
        print(f"Maskly: {spec} is in use by another app; running without the hotkey.", flush=True)
        return
    msg = wintypes.MSG()
    try:
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                try:
                    summon(window)
                except Exception as e:  # one failed press must not kill the hotkey
                    print(f"Maskly: hotkey failed: {e!r}", flush=True)
    finally:
        user32.UnregisterHotKey(None, 1)


def main() -> None:
    spec = os.environ.get("MASKLY_HOTKEY", "ctrl+alt+m")
    mods, vk = parse_hotkey(spec)
    window = webview.create_window("Maskly", serve(), js_api=Api(), width=1280, height=820, min_size=(720, 520))
    hotkey = threading.Thread(target=listen, args=(spec, mods, vk, window), daemon=True)
    hotkey.start()
    webview.start()
    user32.PostThreadMessageW(hotkey.native_id, WM_QUIT, 0, 0)
    hotkey.join(1)


if __name__ == "__main__":
    main()
