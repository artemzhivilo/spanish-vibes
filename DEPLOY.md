# Deploying Spanish Vibes

## The quick version (Railway — recommended)

Railway is the easiest way to get this running on a URL your friend can visit. Free tier gives you $5/month of usage, which is plenty for two people.

### Steps

1. **Push your latest code to GitHub**
   ```bash
   git add -A
   git commit -m "Add deployment config"
   git push
   ```

2. **Go to [railway.app](https://railway.app)** and sign in with GitHub

3. **New Project → Deploy from GitHub Repo → select `spanish-vibes`**

4. **Add your environment variable**
   - Go to the deployed service → **Variables** tab
   - Add: `OPENAI_API_KEY` = your key

   Railway auto-detects the Dockerfile and sets `PORT` for you.

5. **Generate a public URL**
   - Go to **Settings → Networking → Generate Domain**
   - You'll get something like `spanish-vibes-production.up.railway.app`

6. **Send the link to your friend.** Done.

### Notes on Railway
- SQLite database lives on the container's filesystem. It persists between deploys on the same service, but if you delete and recreate the service, the DB resets (which is fine — the app re-seeds automatically).
- For a hobby project with 2 users, the free tier is more than enough.
- The app is currently single-user (no login system), so you and your friend will share the same learning state. If you want separate progress, deploy two instances.

---

## Alternative: Render (also free)

1. Go to [render.com](https://render.com), sign in with GitHub
2. New → Web Service → connect your `spanish-vibes` repo
3. Render auto-detects the Dockerfile
4. Add `OPENAI_API_KEY` env var
5. Deploy

**Caveat:** Render's free tier spins down after 15 minutes of inactivity. First visit after idle takes ~30 seconds to wake up.

---

## Alternative: Fly.io (best for SQLite persistence)

Fly.io supports persistent volumes, so your SQLite database survives redeployments.

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Launch (from project root)
fly launch

# Set your API key
fly secrets set OPENAI_API_KEY=sk-...

# Create a persistent volume for the database
fly volumes create data --size 1

# Deploy
fly deploy
```

You'll need to update the Dockerfile to use `/data/spanish_vibes.db` and mount the volume there. More setup, but better data durability.

---

## Running locally for development

Nothing changes for local dev:

```bash
uv run spanish-vibes
# → http://127.0.0.1:8000
```

Or with reload for development:
```bash
RELOAD=true uv run spanish-vibes
```

---

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | For AI features | none | OpenAI API key. Without it, MCQ generation falls back to offline mode |
| `PORT` | Set by platform | `8000` | Port to listen on |
| `HOST` | No | `127.0.0.1` | Bind address (`0.0.0.0` for containers, set automatically in Dockerfile) |
| `RELOAD` | No | `false` | Enable hot-reload (dev only) |
| `SPANISH_VIBES_DB_PATH` | No | `data/spanish_vibes.db` | Custom database path |
