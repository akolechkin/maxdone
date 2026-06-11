# Production deployment (nginx + gunicorn + Let's Encrypt)

This is **separate** from the dev setup. Dev still runs exactly as before:
`docker compose up` (uses `docker-compose.yml` + runserver). Nothing here touches that.

Production uses `docker-compose.prod.yml` (gunicorn), an `nginx` reverse proxy, and a
`certbot` companion for TLS. Run everything **on the server** with the prod env file:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod <cmd>
```

> Tip: `export COMPOSE_FILE=docker-compose.prod.yml COMPOSE_ENV_FILES=.env.prod` to drop
> the flags from each command.

---

## 1. Configure

```bash
cp .env.prod.example .env.prod
# edit .env.prod: set DOMAIN, EMAIL, DJANGO_SECRET_KEY, POSTGRES_PASSWORD
```

Point your domain's DNS **A/AAAA record at the server** before requesting a cert
(Let's Encrypt validates over HTTP on port 80). Open ports 80 and 443 in the firewall.

## 2. Build & start the app (no TLS yet)

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod build
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d db web
```

`web` runs `migrate` + `collectstatic` automatically on start.

## 3. Bootstrap a temporary cert so nginx can boot

nginx's HTTPS server references cert files that don't exist yet. Create a throwaway
self-signed cert so nginx starts and can serve the ACME challenge:

```bash
DOMAIN=$(grep -E '^DOMAIN=' .env.prod | cut -d= -f2)
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm --entrypoint sh certbot -c "\
  mkdir -p /etc/letsencrypt/live/$DOMAIN && \
  openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
    -keyout /etc/letsencrypt/live/$DOMAIN/privkey.pem \
    -out   /etc/letsencrypt/live/$DOMAIN/fullchain.pem -subj /CN=$DOMAIN"

docker compose -f docker-compose.prod.yml --env-file .env.prod up -d nginx
```

## 4. Issue the real cert — **staging first** (avoid rate limits)

Let's Encrypt has strict rate limits on the production CA. Always dry-run with `--staging`
first; a staging cert is untrusted by browsers but proves the whole flow works.

```bash
DOMAIN=$(grep -E '^DOMAIN=' .env.prod | cut -d= -f2)
EMAIL=$(grep -E '^EMAIL=' .env.prod | cut -d= -f2)

# 4a. STAGING (test issuance end-to-end)
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm \
  --entrypoint certbot certbot certonly --webroot -w /var/www/certbot \
  --staging -d "$DOMAIN" --email "$EMAIL" --agree-tos --no-eff-email
```

If that succeeds, delete the staging cert and request the **production** one:

```bash
# 4b. PRODUCTION (trusted cert)
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm \
  --entrypoint certbot certbot delete --cert-name "$DOMAIN"

docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm \
  --entrypoint certbot certbot certonly --webroot -w /var/www/certbot \
  -d "$DOMAIN" --email "$EMAIL" --agree-tos --no-eff-email

# reload nginx to pick up the real cert
docker compose -f docker-compose.prod.yml --env-file .env.prod exec nginx nginx -s reload
```

Visit `https://$DOMAIN` — it should be valid and proxy to the app.

> Add `www.` (or other hosts) by repeating with extra `-d www.$DOMAIN` flags **and**
> adding them to `DOMAIN`/`server_name` handling as needed.

## 5. Start the whole stack

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

The `certbot` service then runs a **renewal loop** (`certbot renew` every 12h), and
`nginx` **reloads every 6h** to pick up renewed certs — so renewal is automatic. Test it:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm \
  --entrypoint certbot certbot renew --dry-run
```

## 6. Optional hardening (after HTTPS is confirmed)

In `.env.prod`, then `up -d web`:

```ini
DJANGO_SSL_REDIRECT=1          # Django also enforces HTTPS (nginx already redirects)
DJANGO_HSTS_SECONDS=31536000   # 1-year HSTS — only when you're sure HTTPS is permanent
```

---

## Operations

- **Logs:** `docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f web nginx`
- **App update:** `git pull` →
  `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build web`
  (migrate + collectstatic run on start).
- **Recurrence catch-up cron:** the prod stack doesn't include the dev `recur-cron`
  service; add a host crontab entry if you want it, e.g.
  `0 3 * * * cd /path/app && docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T web python manage.py materialize_recurrences`
- **Manual cert renewal + reload:**
  `... run --rm --entrypoint certbot certbot renew && ... exec nginx nginx -s reload`

## What this does NOT change

`docker-compose.yml`, the dev `Dockerfile`, and the runserver dev flow are untouched.
`config/settings.py` gained only **env-driven** prod options whose defaults reproduce the
old dev behavior (DEBUG via `DJANGO_DEBUG`, `ALLOWED_HOSTS` defaults to `*`, the security
block is skipped whenever `DEBUG` is on, which is how dev and the test suite run).
