# Self-hosting on Oracle Cloud "Always Free"

A free alternative to Render (docs/DEPLOYMENT.md §6): the same image runs in Docker Compose on one
Oracle Cloud VM, behind Caddy for HTTPS. The free VM is ARM (Ampere); every base image and every
locked Python dependency is published for ARM64 (checked 2026-09-27). The trade-off against
Render: you manage the VM and backups yourself. This guide assumes no prior Oracle Cloud
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

The instance's subnet → **Security Lists** (or the VNIC's default security list) → Add Ingress
Rules → source CIDR `0.0.0.0/0`, TCP, destination port `80`; repeat for `443`.

Oracle's own tutorials also open ports in the VM's iptables `INPUT` chain. That is for services
running on the host itself; ports Docker publishes are forwarded to the containers without
passing through those rules, so nothing is needed there.

## 3. Point a domain at it

Create a DNS **A record** for the domain or subdomain you'll use (e.g. `learnable.example.com`)
pointing at the VM's public IP. No domain? A free dynamic-DNS subdomain (e.g. DuckDNS) works the
same way. Caddy needs the name to resolve before it can get a certificate.

## 4. Install Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# log out and back in so the group membership takes effect
```

## 5. Deploy

The repository is public, so the VM can clone it without any credentials:

```bash
git clone https://github.com/MrCheope21/LEARNABLE-app.git
cd LEARNABLE-app
cp .env.example .env
```

Edit `.env`:
- Set `AUTH_SECRET` (the comment above it shows how to generate one).
- Uncomment `COMPOSE_FILE` and `DOMAIN`, and set `DOMAIN` to your domain without `https://`.
  `COMPOSE_FILE` makes every `docker compose` command in this directory include
  `deploy/oracle/`, which adds Caddy and derives `PUBLIC_APP_URL` (the address in reset emails)
  from `DOMAIN`.
- Optionally `EMAIL_BACKEND=smtp` + `SMTP_*` for real password-reset emails (docs/DEPLOYMENT.md
  §2), and an `AI_*` provider (docs/AI.md) for AI features.

```bash
docker compose up -d --build
```

This builds `backend/Dockerfile` (web app included; the first build takes several minutes),
starts Postgres, runs migrations, and starts Caddy in front of the app on 80/443. Caddy gets and
renews the Let's Encrypt certificate for `DOMAIN` by itself.

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
docker image prune -f && docker builder prune -af --filter until=168h   # old images, stale build cache
```

## 8. Backups

The database and the uploaded files live in Docker volumes on this VM. From the repository
directory, into `~/backups` (outside the checkout), keeping a week:

```bash
mkdir -p ~/backups
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > ~/backups/db-$(date +%F).sql.gz
docker compose exec -T backend tar czf - -C /app/var documents > ~/backups/documents-$(date +%F).tar.gz
find ~/backups -type f -mtime +7 -delete
```

Copy them off the VM too (e.g. `scp` to your computer, or Oracle Object Storage, which has its
own Always Free quota). To run this from cron, `cd` into the repository first and write `%` as
`\%`.
