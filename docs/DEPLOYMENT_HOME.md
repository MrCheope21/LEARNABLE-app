# Running LEARNABLE at home, with a Google Cloud standby

The site runs on a computer at home and is published through a **Cloudflare Tunnel** (your
computer connects out to Cloudflare; no router ports are opened and no fixed IP is needed). A
script backs the data up every night to a Google Cloud Storage bucket. If the home computer is
down, you start a standby VM on Google Cloud, restore the latest backup there and switch the
address to it. This is a cold standby: the switch is manual, and anything done after the last
backup is lost. There is only ever one live copy of the data.

Every console label below is written from memory; if one has moved, search for its name.

## 0. What you need

- A computer that stays on: Linux, macOS or Windows with Docker (a Raspberry Pi 4/5 with 4 GB or
  more works). Windows users: run the commands inside WSL.
- A **domain managed by Cloudflare** (a few euros a year; a free Cloudflare account). A tunnel
  can't serve a DuckDNS address.
- A Google Cloud account with billing enabled (card needed; set a 1-euro budget alert).

## 1. Home computer

```bash
git clone https://github.com/MrCheope21/LEARNABLE-app.git
cd LEARNABLE-app
cp .env.example .env
```

In `.env`: set `AUTH_SECRET` (the comment above it shows how), uncomment `DOMAIN` and set it to
the address you will use (e.g. `learn.yourdomain.com`), and uncomment the home `COMPOSE_FILE`
and `TUNNEL_TOKEN` lines (step 2 gives the token).

## 2. The tunnel

In Cloudflare: **Zero Trust → Networks → Tunnels → Create a tunnel → Cloudflared**, name it
`learnable-home`. Copy the **token** it shows into `TUNNEL_TOKEN` in `.env`. On the next screen
add a **public hostname**: your `DOMAIN`, service type `HTTP`, URL `backend:8000`.

```bash
docker compose up -d --build
```

Open `https://<DOMAIN>/health`; it should answer `{"status":"ok"}`. The first build takes
several minutes. Docker restarts everything by itself after a reboot, provided Docker starts at
boot.

## 3. Backups to Google

Create a bucket in Google Cloud Storage (Cloud Storage → Create; a region in the US keeps it
within the free allowance, for a few GB). Install rclone (https://rclone.org/install/) and
configure a remote called `gcs`:

```bash
rclone config      # New remote, name: gcs, storage: Google Cloud Storage, follow the prompts
rclone lsd gcs:    # should list your bucket
```

Try a first backup by hand:

```bash
BACKUP_REMOTE=gcs:YOUR-BUCKET deploy/home/backup.sh
```

Then schedule it every night with `crontab -e` (cron has a minimal PATH, so list the folders of
`docker` and `rclone`; `which docker rclone` shows them):

```
PATH=/usr/local/bin:/usr/bin:/bin
0 3 * * * cd /path/to/LEARNABLE-app && BACKUP_REMOTE=gcs:YOUR-BUCKET deploy/home/backup.sh >> ~/learnable-backup.log 2>&1
```

Check `~/learnable-backup.log` now and then; the script stops with an error instead of uploading
a dump that has no schema. It keeps 14 days of copies (`KEEP_DAYS`).

## 4. Standby VM on Google Cloud (prepare once, keep it stopped)

Create a Compute Engine VM: series E2, type **e2-micro**, a `us-central1`, `us-west1` or
`us-east1` region, Ubuntu 24.04 LTS, **Standard** persistent disk of 30 GB. With 1 GB of RAM add
swap before the first build:

```bash
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
curl -fsSL https://get.docker.com | sudo sh && sudo usermod -aG docker $USER   # then reconnect
```

Create a **second tunnel** in Cloudflare called `learnable-google` with **no public hostname**,
and copy its token. On the VM, clone the repository, copy `.env.example` to `.env`, and fill it
exactly like the home one **except `TUNNEL_TOKEN`, which is the Google tunnel's**, and use the
same `AUTH_SECRET` (otherwise everyone is signed out). Also configure rclone with the same
`gcs` remote, then build once and stop the VM:

```bash
docker compose build
```

Then stop the VM in the console. A stopped VM costs nothing for compute; check the Billing page
the first days, since Google's free allowance has limits I could not confirm.

## 5. When the home computer is down

1. Start the VM in the Google console and open its SSH window.
2. `cd LEARNABLE-app && BACKUP_REMOTE=gcs:YOUR-BUCKET deploy/home/restore.sh`
3. Check the VM's own tunnel is healthy in Cloudflare (Tunnels shows `learnable-google` as
   connected).
4. In Cloudflare, **remove the public hostname from `learnable-home` and add it to
   `learnable-google`** (same `DOMAIN`, URL `backend:8000`). If Cloudflare complains that a DNS
   record exists, delete the `DOMAIN` CNAME in the DNS page first and add the hostname again.
5. Open `https://<DOMAIN>/health`.

Because the hostname now belongs to the Google tunnel, the home computer can come back online
without taking any traffic, so the two copies never both serve users.

## 6. Going back home

1. Stop the stack on Google (`docker compose stop`) and run a backup there:
   `BACKUP_REMOTE=gcs:YOUR-BUCKET deploy/home/backup.sh`.
2. On the home computer run `deploy/home/restore.sh` (it replaces its data with that backup).
3. In Cloudflare move the public hostname back to `learnable-home`.
4. Stop the Google VM.

Skip step 1-2 only if nothing was done on the Google copy.

## Limits to know

- A failover loses everything since the last nightly backup (up to a day).
- Restoring deletes the data of the machine you restore on; never run it on the live one.
- Backups are not encrypted by this script. The bucket should stay private, and it contains
  password hashes and study material.
- The free e2-micro is slow and has little memory; it is a rescue machine, not a second home.
