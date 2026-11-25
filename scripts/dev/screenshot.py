"""Full-page screenshots at exact widths and color schemes (dev only).

Drives headless Chrome over the DevTools protocol so narrow phone widths render
truly (a plain --window-size can't go below about 500px).

Needs:  pip install websocket-client   (dev only; the site itself uses none)
Usage:  python scripts/dev/screenshot.py URL OUT_DIR NAME [--widths 390,768,1280,1600] [--modes light,dark]
"""
import argparse
import base64
import json
import os
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket  # websocket-client

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]


class CDP:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=60, suppress_origin=True)
        self.n = 0

    def call(self, method, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("out")
    ap.add_argument("name")
    ap.add_argument("--widths", default="390,768,1280,1600")
    ap.add_argument("--modes", default="light,dark")
    ap.add_argument("--port", type=int, default=9333)
    args = ap.parse_args()

    chrome = next(p for p in CHROME_PATHS if os.path.exists(p))
    profile = tempfile.mkdtemp(prefix="vd-cdp-")
    proc = subprocess.Popen([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                             f"--remote-debugging-port={args.port}", f"--user-data-dir={profile}", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{args.port}/json"))
                page = next(t for t in tabs if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.2)
        cdp = CDP(page["webSocketDebuggerUrl"])
        cdp.call("Page.enable")
        Path(args.out).mkdir(parents=True, exist_ok=True)
        for w in [int(x) for x in args.widths.split(",")]:
            for mode in args.modes.split(","):
                cdp.call("Emulation.setDeviceMetricsOverride", width=w, height=900, deviceScaleFactor=1, mobile=w < 768)
                cdp.call("Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": mode}])
                cdp.call("Page.navigate", url=args.url)
                time.sleep(1.5)
                cdp.call("Runtime.evaluate", expression="document.fonts.ready", awaitPromise=True)
                # Scroll through so scroll-in motion settles, then return to the top.
                cdp.call("Runtime.evaluate", awaitPromise=True, expression="""(async()=>{
                  for(let y=0;y<document.documentElement.scrollHeight;y+=600){scrollTo(0,y);await new Promise(r=>setTimeout(r,60))}
                  document.querySelectorAll('.stamp,.mark').forEach(e=>e.classList.add('is-in'));
                  scrollTo(0,0); await new Promise(r=>setTimeout(r,1300));})()""")
                metrics = cdp.call("Page.getLayoutMetrics")
                size = metrics["cssContentSize"]
                overflow = cdp.call("Runtime.evaluate", expression="document.documentElement.scrollWidth > innerWidth")["result"]["value"]
                shot = cdp.call("Page.captureScreenshot", format="png", captureBeyondViewport=True,
                                clip={"x": 0, "y": 0, "width": w, "height": size["height"], "scale": 1})
                path = Path(args.out) / f"{args.name}-{w}-{mode}.png"
                path.write_bytes(base64.b64decode(shot["data"]))
                print(f"{path.name}  {w}x{int(size['height'])}  horizontal overflow: {overflow}")
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
