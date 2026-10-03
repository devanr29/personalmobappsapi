# VPS Migration — Railway + Neon → VPS (Docker Compose + Postgres + Caddy)

> **For Claude Code running on the VPS:** follow the runbook below step by
> step. Stop and ask the user before any destructive step (pg_restore
> `--clean`, stopping Railway, deleting anything). Never print secret values
> from `.env` back into the terminal or commit them.

## Why
- Railway's trial idles the container → ~20s cold starts, and the account
  had to be rotated monthly.
- Neon is in a far region → 2-3s per TCP+TLS handshake (the reason `db.py`
  pools connections).
- The VPS (2 vCPU / 4 GB / 60 GB, Ubuntu 24.04, Indonesia) is always on and
  puts Postgres on localhost.

## Architecture
```
Phone (Expo app) ──HTTPS──▶ <ip-dashed>.sslip.io :443
                              │
                     VPS (Docker Compose)
                     ├─ caddy   :80/:443  auto Let's Encrypt → api:8000
                     ├─ api     gunicorn app:app (1 worker, scheduler in-process)
                     └─ db      postgres:17, named volume, NOT published
                                 └─ nightly pg_dump → ~/backups (14 days)
```

Files: `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `Caddyfile`,
`.env.example`, `deploy/backup.sh`.

Invariants:
- **Exactly 1 gunicorn worker.** APScheduler runs in-process (`app.py`,
  `scheduler.py`); more workers = duplicate reminders/alerts/quotes.
- **Never add `ports:` to `db`.** Docker-published ports bypass ufw.
- **No app code changes needed.** `db.py` uses Postgres when `DATABASE_URL`
  is set (compose sets it); `config.py` reads secrets from env; the Google
  OAuth token lives in `bot_state` and moves with the data.

## Runbook

### 1. Prerequisites (Docker + firewall)
```bash
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"     # then log out and back in
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
docker run --rm hello-world         # sanity check
```

### 2. Code + secrets
```bash
mkdir -p ~/apps && cd ~/apps
git clone https://github.com/devanr29/personalmobappsapi.git nocturne
cd nocturne
cp .env.example .env
chmod 600 .env
nano .env
```
- Fill values from the Railway dashboard (user pastes them — don't echo them).
- `POSTGRES_PASSWORD`: generate with `openssl rand -hex 24`.
- `API_HOST`: public IP with dashes + `.sslip.io` (get IP with `curl -4 ifconfig.me`).
- Keep `ENABLE_SCHEDULER=0` until cutover.

### 3. First start
```bash
docker compose up -d --build
docker compose ps
docker compose logs -f api      # Ctrl+C to stop following
curl -s https://$(grep ^API_HOST .env | cut -d= -f2)/api/health
```
Expect `{"status":"ok"}` (wrapped in the app's `_ok` envelope). On first
boot `init_db()` creates an empty schema — fine, the restore replaces it.

If Caddy fails to get a certificate: check ports 80/443 are open in ufw
**and** in the VPS provider's cloud firewall/security group.

### 4. Migrate data from Neon
Use Neon's **direct** connection string (host without `-pooler`). The
`pg_dump` major version must be ≥ the Neon server version — check with
`SELECT version();` in Neon; if Neon is 18, use `postgres:18` below (and
in compose).
```bash
read -rs NEON_URL      # paste the Neon URL, not echoed
docker run --rm postgres:17 pg_dump "$NEON_URL" -Fc > ~/neon.dump
ls -lh ~/neon.dump

docker compose stop api        # nothing writing during the restore
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner --no-acl' < ~/neon.dump
docker compose start api
```
Verify row counts match Neon:
```bash
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "\dt"'
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT (SELECT count(*) FROM bot_state) bot_state, (SELECT count(*) FROM reminders) reminders, (SELECT count(*) FROM notes) notes"'
```
Run the same counts against Neon (`docker run --rm -it postgres:17 psql "$NEON_URL"`).

### 5. Verify
From the VPS or the laptop:
```bash
python3 scripts/smoke.py --url https://<API_HOST> --token <MOBILE_API_TOKEN>
```
All routes should pass. Also check RAM: `docker stats --no-stream`.

### 6. Cutover (ask the user first)
1. Re-run step 4 right before switching so no Railway-side writes are lost.
2. User stops the Railway service (dashboard).
3. Set `ENABLE_SCHEDULER=1` in `.env`, then `docker compose up -d`.
4. Phone: **Settings → API URL** → `https://<API_HOST>` (runtime override in
   `mobile/src/api/client.ts`, no rebuild needed).
5. Later: update `EXPO_PUBLIC_API_URL` for EAS builds; delete `railway.toml`.
6. Keep Neon ~1 week as a rollback point, then retire it.

### 7. Backups
```bash
chmod +x deploy/backup.sh
./deploy/backup.sh                      # test once
crontab -e
# add:
0 3 * * * /home/devanr2911/apps/nocturne/deploy/backup.sh >> /home/devanr2911/backups/backup.log 2>&1
```
Test a restore into a scratch DB once:
```bash
docker compose exec db sh -c 'createdb -U "$POSTGRES_USER" restore_test'
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d restore_test --no-owner' < ~/backups/nocturne-$(date +%F).dump
docker compose exec db sh -c 'dropdb -U "$POSTGRES_USER" restore_test'
```
Optional follow-up: copy `~/backups` off-box (rclone → Google Drive).

## Day-to-day
- Code changes are made on the laptop (DEV), pushed, then on the VPS:
  `cd ~/apps/nocturne && git pull && docker compose up -d --build`
- Logs: `docker compose logs -f api` (also `/logs?secret=...` and the Sheets log).
- Restart: `docker compose restart api`. Reboots auto-recover (`restart: unless-stopped`).

## Known caveats
- sslip.io URL is tied to the VPS IP; switching to a real domain later only
  changes `API_HOST`.
- `bot_all.log` lives inside the container and is lost on rebuild (the
  `/logs` viewer resets). Persisting it needs a small `logging_setup.py`
  path change — out of scope for now.
- `.env` holds real secrets: `chmod 600`, never commit.

## Verification checklist
- [ ] `docker compose ps` — db healthy, api + caddy running
- [ ] `curl -I https://<API_HOST>/api/health` → 200, valid cert
- [ ] `scripts/smoke.py` passes
- [ ] Phone loads Home + Budget fast (no ~20s first hit)
- [ ] A test reminder pushes exactly once
- [ ] `sudo reboot` → everything comes back
- [ ] Next morning a `.dump` exists in `~/backups`
