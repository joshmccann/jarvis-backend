# JARVIS backend

The always-on brain behind the JARVIS dashboard. Serves the dashboard, answers you
live with Claude, speaks in your custom Fish Audio voice, and runs real actions
(send today's reel scripts to Telegram). Pure Python stdlib — no pip installs.

## What you create (Claude can't create accounts or pay)
1. **A VPS** — Hetzner CX22 (~$5/mo) or DigitalOcean ($6). Pick Ubuntu 24.04.
2. **Fish Audio** — sign up at fish.audio, make an API key, and clone/pick a "Jarvis"
   voice (grab its reference id). This is the custom voice.

You already have the Anthropic API key (in `reel-remix/.secrets.json`) and the
Telegram bot — reuse both.

## Deploy (one paste, in the VPS web console)
```
curl -fsSL https://raw.githubusercontent.com/joshmccann/jarvis-backend/main/install.sh | bash
nano /opt/jarvis/.env      # paste your keys
systemctl restart jarvis
```
Open `http://YOUR_SERVER_IP:8080` — dashboard + voice output + typing work now.

## Talking to it (mic needs HTTPS)
Browsers only give the mic to https pages. Free fix, no domain needed:
`cloudflared tunnel --url http://localhost:8080` gives an https URL you open on your
monitor. (Or point a domain at the box and add Caddy for auto-TLS.)

## Endpoints
- `GET /` dashboard · `GET /state` live data · `GET /briefing` spoken rundown
- `POST /ask {text}` live Claude answer, spoken · `POST /action/scripts` send scripts to Telegram
- `GET /health` shows whether brain + voice keys are wired

## Keeping data live
`data.json` (gitignored) is the snapshot the brain reasons over. A small sync job
(Notion/Gmail pull) can rewrite it on a schedule; until then it uses the seed in server.py.
