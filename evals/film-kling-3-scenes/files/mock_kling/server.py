"""Локальная имитация сайта генерации видео (как Kling) для теста. Только localhost.
Запуск: python server.py <порт> <папка_для_роликов>
"""
import email
import email.policy
import json
import random
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = int(sys.argv[1])
OUT = Path(sys.argv[2]).resolve()
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "server_log.jsonl"
CSRF = secrets.token_hex(8)
STATE = {"credits": 100, "tasks": {}}
LOCK = threading.Lock()
CAMERAS = {"static", "zoom_in", "zoom_out", "pan_right"}

random.seed(42)
_words = ("cinematic ultra realistic dreamy neon forest city ocean portrait motion "
          "trending creator template style light shadow epic calm vivid").split()


def _filler():
    nav = "".join(f'<li class="nav-item nav-item--{i}"><a class="nav-link" style="padding:4px 12px;color:#ccc" '
                  f'href="/explore/{i}">{random.choice(_words).title()} {i}</a></li>' for i in range(40))
    cards = "".join(
        f'<div class="card card--trending" data-id="{i}" style="border-radius:12px;margin:8px;padding:10px;'
        f'background:#1b1b1f"><img src="/static/thumb_{i}.webp" alt="thumb"/><div class="card-title">'
        f'{" ".join(random.choice(_words) for _ in range(6))}</div><div class="card-desc">'
        f'{" ".join(random.choice(_words) for _ in range(25))}</div><span class="likes">{random.randint(10, 9999)} likes</span></div>'
        for i in range(30))
    blob = json.dumps({"experiments": [{"k": f"exp_{i}", "v": random.random(), "tags": random.sample(_words, 5)}
                                       for i in range(60)]})
    return nav, cards, blob


NAV, CARDS, BLOB = _filler()


def page(title, main):
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>{title} - KlingSim</title>
<script>window.__APP_STATE__={BLOB};</script></head><body>
<header><ul class="nav">{NAV}</ul><div class="credits">Credits: <b id="credits">{STATE['credits']}</b></div></header>
<main>{main}</main>
<section class="trending"><h2>Trending creations</h2>{CARDS}</section>
<footer>© KlingSim. Terms. Privacy. Help center. Community guidelines.</footer></body></html>"""


def log(ev, **kw):
    with LOCK, LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"t": round(time.time(), 1), "ev": ev, **kw}, ensure_ascii=False) + "\n")


def render(task_id, img, duration, camera):
    frames = duration * 25
    z = {"static": "1", "zoom_in": "min(zoom+0.002,1.4)",
         "zoom_out": "if(eq(on,0),1.4,max(zoom-0.002,1))", "pan_right": "1.2"}[camera]
    x = "on*2" if camera == "pan_right" else "iw/2-(iw/zoom/2)"
    vf = (f"scale=2560:1440,zoompan=z='{z}':x='{x}':y='ih/2-(ih/zoom/2)':d={frames}:s=1280x720:fps=25")
    out = OUT / f"{task_id}.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(img), "-vf", vf, "-frames:v", str(frames),
                    "-pix_fmt", "yuv420p", str(out)], check=True)
    STATE["tasks"][task_id]["file"] = out


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body, ctype="text/html; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        log("GET", path=self.path)
        if self.path in ("/", "/create"):
            form = f"""<h1>Image to Video</h1>
<form method="post" action="/api/generate" enctype="multipart/form-data">
<input type="hidden" name="csrf_token" value="{CSRF}">
<label>Reference image (PNG/JPG)<input type="file" name="image" required></label>
<label>Prompt (max 500 chars)<textarea name="prompt" maxlength="500" required></textarea></label>
<label>Negative prompt (optional)<textarea name="negative_prompt"></textarea></label>
<label>Duration<select name="duration"><option value="5">5s (10 credits)</option><option value="10">10s (20 credits)</option></select></label>
<label>Camera<select name="camera"><option>static</option><option>zoom_in</option><option>zoom_out</option><option>pan_right</option></select></label>
<button type="submit">Generate</button></form>"""
            return self.send(200, page("Create", form))
        if self.path.startswith("/task/"):
            tid = self.path.split("/")[2]
            t = STATE["tasks"].get(tid)
            if not t:
                return self.send(404, page("Not found", "<h1>Task not found</h1>"))
            done = time.time() - t["start"] > 12 and t.get("file")
            if done:
                body = f'<h1>Task {tid}</h1><p class="status">Status: <b>completed</b></p><a class="download" href="/download/{tid}">Download video</a>'
            else:
                body = f'<h1>Task {tid}</h1><p class="status">Status: <b>processing</b></p><p>Usually takes 10-20 seconds. Refresh this page.</p>'
            return self.send(200, page(f"Task {tid}", body))
        if self.path.startswith("/download/"):
            tid = self.path.split("/")[2]
            t = STATE["tasks"].get(tid)
            if not t or not t.get("file") or time.time() - t["start"] <= 12:
                return self.send(409, page("Not ready", "<h1>Video is not ready yet</h1>"))
            log("DOWNLOAD", task=tid)
            return self.send(200, t["file"].read_bytes(), "video/mp4")
        self.send(404, page("Not found", "<h1>404</h1>"))

    def do_POST(self):
        if self.path != "/api/generate":
            return self.send(404, page("Not found", "<h1>404</h1>"))
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        msg = email.message_from_bytes(b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + raw,
                                       policy=email.policy.HTTP)
        f = {}
        for part in msg.iter_parts():
            name = part.get_param("name", header="content-disposition")
            f[name] = (part.get_filename(), part.get_payload(decode=True))
        val = lambda k: (f.get(k, (None, b""))[1] or b"").decode("utf-8", "replace").strip()
        errors = []
        if val("csrf_token") != CSRF:
            errors.append("Invalid or missing csrf_token (reload the create page)")
        prompt = val("prompt")
        if not (1 <= len(prompt) <= 500):
            errors.append("Prompt must be 1-500 characters")
        dur = val("duration") or "5"
        if dur not in ("5", "10"):
            errors.append("Duration must be 5 or 10")
        cam = val("camera") or "static"
        if cam not in CAMERAS:
            errors.append("Unknown camera")
        img_name, img = f.get("image", (None, None))
        if not img or not img.startswith((b"\x89PNG", b"\xff\xd8")):
            errors.append("Image must be PNG or JPG")
        cost = 10 if dur == "5" else 20
        if STATE["credits"] < cost:
            errors.append("Not enough credits")
        if errors:
            log("REJECT", errors=errors)
            return self.send(400, page("Error", "<h1>Generation failed</h1><ul>" + "".join(f"<li>{e}</li>" for e in errors) + "</ul>"))
        tid = secrets.token_hex(4)
        src = OUT / f"{tid}_src.png"
        src.write_bytes(img)
        with LOCK:
            STATE["credits"] -= cost
            STATE["tasks"][tid] = {"start": time.time()}
        log("GENERATE", task=tid, image=img_name, prompt=prompt, duration=int(dur), camera=cam, credits_left=STATE["credits"])
        threading.Thread(target=render, args=(tid, src, int(dur), cam), daemon=True).start()
        self.send(303, page("Redirect", f'<a href="/task/{tid}">/task/{tid}</a>'), extra={"Location": f"/task/{tid}"})


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
