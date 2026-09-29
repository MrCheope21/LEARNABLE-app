# Self-hosting on Oracle Cloud "Always Free"

A free alternative to Render (docs/DEPLOYMENT.md): everything runs in Docker Compose on one Oracle
Cloud VM, from the same image the Render deploy builds (`backend/Dockerfile`, one origin for web
+ API). The free VM is ARM (Ampere); every base image and every locked Python dependency is
published for ARM64 (checked 2026-09-27). The trade-off against Render: you manage the VM, HTTPS
and backups yourself instead of a dashboard doing it. This guide assumes no prior Oracle Cloud
experience.

## 0. Before relying on it

- **Idle instances can be stopped.** Oracle may stop Always Free instances it considers idle
  (over 7 days: CPU, network and, on Ampere, memory utilization all under 20% at the 95th
  percentile). A lightly used LEARNABLE easily qualifies. Upgrading the account to Pay As You
  Go exempts it; Always Free resources stay free, but the card on file can then be charged for
  anything created beyond them. A stopped instance keeps its disk: start it again from the
  console and the containers come back on their own. Oracle's Always Free documentation has the
  current rules.
- **Backups are yours** (§8): there is no managed database here.

## 1. Create the VM

1. Sign up at cloud.oracle.com. The **home region** can't be changed later and is where Always
   Free VMs run: pick one near your users (e.g. Milan or Frankfurt). A card is required for
   identity verification; Always Free resources are never billed.
2. Compute → Instances → **Create instance**.
3. **Shape** → Change shape → Ampere → `VM.Standard.A1.Flex`. Always Free covers up to 4 OCPUs /
   24 GB RAM in total across your Ampere instances; one instance using all of it is fine. If
   creation fails with *Out of host capacity*, the region has no free Ampere capacity right
   now: retry later, or with fewer OCPUs.
4. **Image**: Ubuntu (the latest LTS marked Always Free eligible).
5. **Add SSH key**: let Oracle generate one and download the private key, or paste your own
   public key.
6. Boot volume: the default size is within the Always Free 200 GB total. Create.
7. Note the instance's **public IP** once it's running, and SSH in as `ubuntu`.

## 2. Open ports 80 and 443

**Oracle's cloud firewall** blocks them: the instance's subnet → **Security Lists** (or the
VNIC's default security list) → Add Ingress Rules → source CIDR `0.0.0.0/0`, TCP, destination
port `80`; repeat for `443`.

**The VM's own firewall**: Oracle's Ubuntu image also ships iptables rules that reject new
connections except SSH. Docker adds its own rules for the ports it publishes, but open 80/443
here too so the setup doesn't depend on rule order. Do it before installing Docker, so the saved
rules don't capture Docker's:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

## 3. Point a domain at it

Create a DNS **A record** for the domain or subdomain you'll use (e.g. `learnable.example.com`)
pointing at the VM's public IP. No domain? A free dynamic-DNS subdomain (e.g. DuckDNS) works the
same way. Caddy (§5) needs the name to resolve before it can get a certificate.

## 4. Install Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# log out and back in so the group membership takes effect
docker compose version   # must be 2.24+ (the overlay uses `!reset` to unpublish 8000 and 5432)
```

## 5. Deploy

The repository is public, so the VM can clone it without any credentials:

```bash
git clone https://github.com/MrCheope21/LEARNABLE-app.git
cd LEARNABLE-app
cp .env.example .env
```

Edit `.env`:
- `AUTH_SECRET`: generate with `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.
- `PUBLIC_APP_URL=https://learnable.example.com` (your domain, with `https://`).
- `DOMAIN=learnable.example.com` (same domain, no scheme; read by `deploy/oracle/Caddyfile`).
- Add `COMPOSE_FILE=docker-compose.yml:deploy/oracle/docker-compose.oracle.yml`. Every
  `docker compose` command in this directory then includes the overlay; without it, a plain
  `docker compose up` would publish the backend and Postgres again and drop HTTPS.
- Optionally `EMAIL_BACKEND=smtp` + `SMTP_*` for real password-reset emails (docs/DEPLOYMENT.md
  §2), and an `AI_*` provider (docs/AI.md) for AI features.

```bash
docker compose up -d --build
```

This builds `backend/Dockerfile` (web app included; the first build takes several minutes),
starts Postgres, runs migrations, and starts Caddy in front of the app on 80/443. Caddy requests
and renews its Let's Encrypt certificate for `DOMAIN` by itself.

## 6. Verify

```bash
curl https://learnable.example.com/health   # {"status":"ok"}
```

Then open `https://learnable.example.com/` in a browser: the app itself, on the same origin as
the API. If HTTPS fails, `docker compose logs caddy` shows why (usually the A record doesn't
point at the VM yet, or port 80 is still closed in the security list).

## 7. Updating

```bash
git pull
docker compose up -d --build
docker image prune -f   # every build leaves the previous image behind
```

## 8. Backups

Data lives in two Docker volumes on this VM: the database and the uploaded files. From the
repository directory:

```bash
docker compose exec -T postgres pg_dump -U postgres adaptive_learning | gzip > db-$(date +%F).sql.gz
docker compose cp backend:/app/var/documents ./documents-$(date +%F)
```

Copy both off the VM (e.g. `scp` to your computer, or Oracle Object Storage, which has its own
Always Free quota). To run this from cron, write `%` as `\%`.
