#!/usr/bin/env python3
"""
JARVIS backend — the brain behind the dashboard.

Runs 24/7 on a cheap VPS. The dashboard (served at /) talks to it:
  GET  /briefing        -> {text, audio}  the spoken daily rundown (Jarvis voice)
  POST /ask   {text}     -> {text, audio, action?}  live answer from Claude, spoken
  POST /action/scripts   -> sends the latest reel scripts to Telegram

Voice = Fish Audio (custom Jarvis clone). Brain = Claude (Anthropic API).
Every secret comes from the environment (.env) — nothing is hard-coded.
"""
import base64, json, os, glob, urllib.request, urllib.parse
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = Path(__file__).resolve().parent

def env(k, d=""): return os.environ.get(k, d)
ANTHROPIC_KEY = env("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = env("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
FISH_KEY = env("FISH_API_KEY")
FISH_VOICE = env("FISH_VOICE_ID", "7c1a7dc37829497593ab4db29eed387c")  # Josh's cloned Jarvis voice
TG_TOKEN = env("TELEGRAM_TOKEN")
TG_CHAT = env("TELEGRAM_CHAT")
REMIX_DIR = Path(env("REMIX_DIR", str(HERE.parent / "_remix")))

# --- live context the brain reasons over. A cron/sync job can rewrite data.json. ---
def context():
    f = HERE / "data.json"
    if f.exists():
        return json.loads(f.read_text())
    return {  # seed snapshot until the sync job overwrites data.json
        "deals": {"active": 16, "pipeline_asking": 86220, "to_send": 3,
                  "hot": "Lovable $12k (reply overdue)", "flag": "verify Zaro.ai before any payment"},
        "reels": {"posted": 1, "ready": 7, "with_editor": 1, "to_film": 6,
                  "blocked": "Facebook reel needs Josh's on-cam photo"},
        "bynoon": {"calls": ["Thu 24 Jul 2:00 PM discovery", "Fri 25 Jul 10:30 AM strategy"],
                   "note": "sample bookings until the calendar is connected"},
        "radar": {"competitors": 19, "next_scan": "Wednesday"},
    }

JARVIS_SYSTEM = (
    "You are JARVIS, Josh McCann's calm, dry, capable AI chief of staff for his content business "
    "(brand monopolymccann) and his agency By Noon. Speak in short, natural spoken sentences — this is "
    "read aloud, so no markdown, no lists, no emojis, no em dashes. Be concise and warm, a touch witty. "
    "Answer from the CONTEXT JSON provided. If Josh asks you to DO something you can actually do, end your "
    "reply with a marker on its own: [ACTION:send_scripts] to send today's reel scripts to his Telegram, or "
    "[ACTION:run_radar] to run the breakout radar. Only use a marker when he clearly asks for that action."
)

def http_json(url, payload, headers, method="POST"):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())

def claude(user_text, history=None):
    if not ANTHROPIC_KEY:
        return "My brain isn't wired up yet. Add the Anthropic key to the server and I'll be right with you."
    msgs = (history or []) + [{"role": "user", "content": user_text}]
    sys = JARVIS_SYSTEM + "\n\nCONTEXT:\n" + json.dumps(context())
    out = http_json("https://api.anthropic.com/v1/messages",
        {"model": ANTHROPIC_MODEL, "max_tokens": 400, "system": sys, "messages": msgs},
        {"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    return "".join(b.get("text", "") for b in out.get("content", [])).strip()

def fish_tts(text):
    """Fish Audio TTS -> base64 mp3. Returns '' if not configured (dashboard falls back to browser voice)."""
    if not (FISH_KEY and FISH_VOICE):
        return ""
    try:
        body = json.dumps({"text": text, "reference_id": FISH_VOICE, "format": "mp3"}).encode()
        req = urllib.request.Request("https://api.fish.audio/v1/tts", data=body,
            headers={"Authorization": f"Bearer {FISH_KEY}", "content-type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            return base64.b64encode(r.read()).decode()
    except Exception as e:
        print("fish_tts error:", e); return ""

def telegram(text):
    if not (TG_TOKEN and TG_CHAT):
        return False
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            data=urllib.parse.urlencode({"chat_id": TG_CHAT, "text": text}).encode()), timeout=30)
        return True
    except Exception as e:
        print("telegram error:", e); return False

def send_scripts():
    files = sorted(glob.glob(str(REMIX_DIR / "*" / "SCRIPT.txt")), key=os.path.getmtime, reverse=True)[:3]
    if not files:
        return "I couldn't find any scripts to send yet. Drop me the reel links and I'll write them first."
    for i, f in enumerate(reversed(files), 1):
        telegram(f"Script {i} of {len(files)}\n\n" + Path(f).read_text())
    return f"Done. I've sent {len(files)} scripts to your Telegram."

def briefing_text():
    c = context()
    return claude("Give me my full briefing now: creator side first (deals then reels), then the By Noon "
                  "business side with the booked calls, then what to do first today. Keep it to a natural "
                  "spoken paragraph.") if ANTHROPIC_KEY else (
        f"Welcome back, Josh. {c['deals']['active']} active deals, about {c['deals']['pipeline_asking']//1000} "
        f"thousand in the pipeline, {c['deals']['to_send']} drafts ready to send. {c['reels']['ready']} reels "
        f"ready, {c['reels']['to_film']} to film. By Noon has {len(c['bynoon']['calls'])} calls booked this week. "
        "Where do you want to start?")

def do_action(reply):
    if "[ACTION:send_scripts]" in reply:
        return reply.replace("[ACTION:send_scripts]", "").strip(), send_scripts()
    if "[ACTION:run_radar]" in reply:
        return reply.replace("[ACTION:run_radar]", "").strip(), "run_radar"
    return reply, None

class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "content-type")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_OPTIONS(self): self._send(204, b"")
    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            return self._send(200, (HERE / "static" / "index.html").read_bytes(), "text/html")
        if self.path.startswith("/static/"):
            p = HERE / self.path.lstrip("/")
            if p.exists():
                ct = "image/jpeg" if p.suffix in (".jpg", ".jpeg") else "application/octet-stream"
                return self._send(200, p.read_bytes(), ct)
        if self.path == "/briefing":
            t = briefing_text(); return self._send(200, {"text": t, "audio": fish_tts(t)})
        if self.path == "/state":
            return self._send(200, context())
        if self.path == "/health":
            return self._send(200, {"ok": True, "brain": bool(ANTHROPIC_KEY), "voice": bool(FISH_KEY and FISH_VOICE)})
        return self._send(404, {"error": "not found"})
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); raw = self.rfile.read(n) if n else b"{}"
        try: data = json.loads(raw or b"{}")
        except Exception: data = {}
        if self.path == "/ask":
            reply = claude(data.get("text", "")); reply, act = do_action(reply)
            note = send_scripts() if act == "run_radar" else None  # radar handled elsewhere for now
            spoken = reply + (" " + note if isinstance(note, str) else "")
            return self._send(200, {"text": spoken, "audio": fish_tts(spoken), "action": act})
        if self.path == "/action/scripts":
            msg = send_scripts(); return self._send(200, {"text": msg, "audio": fish_tts(msg)})
        return self._send(404, {"error": "not found"})
    def log_message(self, *a): pass

if __name__ == "__main__":
    port = int(env("PORT", "8080"))
    print(f"JARVIS backend on :{port}  brain={bool(ANTHROPIC_KEY)} voice={bool(FISH_KEY and FISH_VOICE)}")
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
