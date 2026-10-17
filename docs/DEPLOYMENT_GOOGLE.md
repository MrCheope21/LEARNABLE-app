# LEARNABLE su Google Cloud (VM e2-micro gratuita)

Un solo server piccolo, sempre acceso, con HTTPS automatico, backup giornalieri sul server e
una copia automatica sul tuo Mac ogni volta che si connette a internet. Costo: 0 € restando
nei limiti gratuiti di Google.

## 0. Cosa devi sapere prima

- **Gratuito ma non garantito per sempre.** Il piano "Always Free" di Google può cambiare:
  controlla docs.cloud.google.com/free. Per questo i backup sul Mac sono parte del progetto.
- **È gratis solo se rispetti tre condizioni**: macchina `e2-micro`, regione `us-west1`,
  `us-central1` o `us-east1`, disco di tipo "Standard" (non SSD) fino a 30 GB. Il traffico in
  uscita oltre 1 GB al mese si paga (pochi centesimi): per uso personale è improbabile.
- **Serve una carta** (anche prepagata) per attivare l'account. Imposta in Google Cloud un
  **budget con avviso a 1 €** (Fatturazione → Budget e avvisi) per accorgerti subito di
  eventuali costi.
- L'app usa **SQLite** su questo server (una persona sola, niente PostgreSQL: la VM ha solo
  1 GB di RAM). Il database e i file caricati stanno in un unico volume Docker.
- Le **registrazioni sono chiuse** (`REGISTRATION_OPEN=false`): nessun estraneo può creare un
  account e consumare la tua quota di IA. Per far entrare una persona: mettilo a `true`,
  riavvia, fai registrare, rimettilo a `false`.

## 1. Crea la VM

1. console.cloud.google.com → crea un progetto → Compute Engine → **Crea istanza**.
2. Regione **us-central1** (o us-west1 / us-east1), tipo macchina **e2-micro**.
3. Disco di avvio: Debian 12, tipo **Disco permanente standard**, 30 GB.
4. Firewall: spunta **Consenti traffico HTTP** e **Consenti traffico HTTPS**.
5. Crea. Poi Rete VPC → Indirizzi IP → **Riserva un indirizzo IP statico** per la VM (resta
   gratuito finché è collegato a una VM accesa).

## 2. Punta il nome DuckDNS alla VM

Su duckdns.org imposta l'IP di `learnable` all'indirizzo statico della VM.

## 3. Collegati e prepara il server

Dalla console Google clicca **SSH** accanto alla VM, poi:

```sh
curl -fsSL https://raw.githubusercontent.com/MrCheope21/LEARNABLE-app/main/deploy/google/setup-vm.sh -o setup-vm.sh
sh setup-vm.sh
```

(se la cartella non è ancora su `main`, usa il nome del ramo al posto di `main`). Esci e
rientra con SSH.

## 4. Configura (i segreti li scrivi tu, qui sul server)

```sh
cd ~/LEARNABLE-app
git checkout feature-community      # finché la PR non è unita a main
sh deploy/google/make-env.sh learnable.duckdns.org
nano .env                           # incolla AI_API_KEY (la tua chiave Gemini), salva
```

## 5. Avvia

```sh
docker compose -f deploy/google/docker-compose.yml --env-file .env up -d --build
```

La prima volta la costruzione richiede 10–20 minuti (la VM è piccola; lo swap evita errori
di memoria). Poi apri https://learnable.duckdns.org e controlla che compaia la pagina di
accesso.

## 6. Porta i tuoi dati dal Mac

Non devi creare un account sul server: i tuoi utenti arrivano insieme ai dati.

1. Sul server: `docker compose -f deploy/google/docker-compose.yml stop backend`
2. Sul Mac (dalla cartella del repo):
   `sh deploy/google/push-data.sh TUOUTENTE@IP_DELLA_VM`
   (copia database e file; sul server resta una copia di sicurezza nella cartella `old`
   del volume).
3. Sul server: `docker compose -f deploy/google/docker-compose.yml up -d`
4. Apri il sito ed entra con la **stessa email e password** di sempre.

Per accedere via SSH dal Mac da terminale usa la chiave che Google ti fa creare
(Compute Engine → Metadati → Chiavi SSH) oppure `gcloud compute ssh`.

## 7. Backup sul Mac ogni volta che va online

```sh
sh scripts/install-backup-agent.sh TUOUTENTE@IP_DELLA_VM [percorso/chiave-ssh]
```

Ogni 30 minuti e a ogni cambio di rete (anche sotto hotspot) il Mac controlla se sul server
c'è un backup più recente e lo scarica in `~/LEARNABLE-backups` (ultime 30 copie). Se non c'è
internet non fa nulla. Sul server un backup parte ogni notte alle 03:17 e conserva 14 giorni
in `~/backups`.

**Ripristino:** `tar -xzf learnable-DATA.tar.gz` dà `learnable.db` e `documents/`. Metti la
cartella in un nuovo server con `push-data.sh` (modificalo per usare quel file) oppure copiali
in `backend/` per usarli in locale.

## 8. Aggiornare l'app in seguito

```sh
cd ~/LEARNABLE-app && git pull
docker compose -f deploy/google/docker-compose.yml --env-file .env up -d --build
```

Le migrazioni del database partono da sole all'avvio. Prima di un aggiornamento importante
esegui `sh deploy/google/backup-on-server.sh`.

## 9. Se qualcosa non va

- `docker compose -f deploy/google/docker-compose.yml logs --tail 50 backend`
- Il sito non si apre: controlla che l'IP in DuckDNS sia quello della VM e che le porte
  80/443 siano consentite.
- Memoria esaurita: `free -m`; lo swap da 2 GB è creato da `setup-vm.sh`.
- Email di reset password: con `EMAIL_BACKEND=console` il link compare nei log del server
  (`docker compose ... logs backend`). Per l'invio vero serve un provider SMTP.
