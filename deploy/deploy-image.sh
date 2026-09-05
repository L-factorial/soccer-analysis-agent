#!/usr/bin/env bash
# Installed as /usr/local/sbin/soccer-deploy; forced command for the CI SSH key.
set -euo pipefail

if [[ ! ${SSH_ORIGINAL_COMMAND:-} =~ ^deploy\ (sha256:[a-f0-9]{64})$ ]]; then
    echo 'Expected: deploy sha256:<64 lowercase hexadecimal digits>' >&2
    exit 2
fi
image="ghcr.io/l-factorial/soccer-analysis-agent-backend@${BASH_REMATCH[1]}"
cd /opt/soccer-analysis-agent
exec 9>/var/lock/soccer-backend-deploy.lock
flock -w 300 9
test -f .env
test -f compose.yaml

# Pull while the previous backend continues serving requests.
docker pull "$image"
docker image inspect "$image" > /dev/null
cp -p .env .env.previous

rollback() {
    trap - ERR INT TERM HUP
    echo 'Deployment failed; restoring the previous image.' >&2
    cp -p .env.previous .env
    if ! docker compose up -d --no-build --pull never --wait --wait-timeout 90; then
        echo 'Rollback failed; inspect the backend on the droplet.' >&2
    fi
    exit 1
}
trap rollback ERR INT TERM HUP
umask 077
sed '/^BACKEND_IMAGE=/d' .env > .env.next
printf 'BACKEND_IMAGE=%s\n' "$image" >> .env.next
mv .env.next .env
docker compose up -d --no-build --pull never --wait --wait-timeout 90
curl --fail --silent --show-error --retry 3 --retry-delay 2 --retry-all-errors --max-time 15 \
    http://127.0.0.1:8000/health
curl --fail --silent --show-error --retry 3 --retry-delay 2 --retry-all-errors --max-time 15 \
    --resolve api.soccer-agent.lfactorial.com:443:127.0.0.1 \
    https://api.soccer-agent.lfactorial.com/health
trap - ERR INT TERM HUP
printf '\nDeployed %s\n' "$image"
