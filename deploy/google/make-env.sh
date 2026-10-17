#!/bin/sh
# Writes ~/LEARNABLE-app/.env for the server with a fresh random AUTH_SECRET. The AI key is NOT
# asked for or written: add it yourself with  nano .env  (never paste it into a chat).
# Usage:  sh deploy/google/make-env.sh learnable.duckdns.org
set -eu
DOMAIN="${1:?usage: make-env.sh your.domain.name}"
ENV="$(dirname "$0")/../../.env"
[ ! -f "$ENV" ] || { echo ".env already exists: edit it by hand."; exit 1; }
SECRET="$(head -c 48 /dev/urandom | base64 | tr -d '/+=\n' | head -c 64)"
umask 077
cat > "$ENV" <<ENVEOF
DOMAIN=$DOMAIN
AUTH_SECRET=$SECRET
PUBLIC_APP_URL=https://$DOMAIN
# Nobody else can create accounts. Set to true only to let someone in, then back to false.
REGISTRATION_OPEN=false
EMAIL_BACKEND=console

# AI: fill in with nano. Same values as your local .env.
AI_PROVIDER=gemini
AI_MODEL=gemini-3.5-flash-lite
AI_API_KEY=
ENVEOF
echo ".env written (mode 600). Now: nano .env  and paste your AI_API_KEY."
