#!/usr/bin/env bash
# Prepare a fresh Ubuntu 22.04/24.04 VM to run DevPilot. Run once as root (or with sudo):
#   sudo DEPLOY_PUBKEY="ssh-ed25519 AAAA... you@laptop" REPO_URL=git@github.com:OWNER/DevPilot-AI.git \
#     ./scripts/vm-bootstrap.sh
#
# What it does: non-root `deploy` user (key-only SSH), SSH hardening, ufw (22/80/443), Docker with
# log rotation, /opt/devpilot checkout, systemd unit, logrotate, nightly DB backup, auto security
# updates. SAFETY: keep your current SSH session open and test `ssh deploy@<vm>` in a second
# terminal before logging out, since password and root SSH login are disabled at the end.
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "run as root: sudo $0"; exit 1; }
: "${DEPLOY_PUBKEY:?set DEPLOY_PUBKEY to the public key the deploy user (and CI) will use}"
REPO_URL="${REPO_URL:-}"
APP_DIR=/opt/devpilot
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl git ufw logrotate \
  unattended-upgrades cron awscli || DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates curl git ufw logrotate unattended-upgrades cron   # awscli: ECR pulls only

# Docker + log rotation
command -v docker >/dev/null || curl -fsSL https://get.docker.com | sh
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'JSON'
{ "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "3" } }
JSON
systemctl enable --now docker && systemctl restart docker

# Deploy user: no password, SSH key only, can run docker
id deploy >/dev/null 2>&1 || useradd --create-home --shell /bin/bash deploy
usermod -aG docker deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
echo "$DEPLOY_PUBKEY" > /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys && chmod 600 /home/deploy/.ssh/authorized_keys

# App checkout and directories
if [ -n "$REPO_URL" ] && [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
elif [ ! -d "$APP_DIR" ]; then
  cp -r "$SRC_DIR" "$APP_DIR"
fi
chown -R deploy:deploy "$APP_DIR"
install -d -o deploy -g deploy /var/log/devpilot /var/backups/devpilot
[ -f "$APP_DIR/.env" ] || { cp "$APP_DIR/deploy/vm/env.prod.example" "$APP_DIR/.env"; \
  chown deploy:deploy "$APP_DIR/.env"; chmod 600 "$APP_DIR/.env"; }

# systemd unit, logrotate, nightly backup
install -m 644 "$APP_DIR/deploy/vm/devpilot.service" /etc/systemd/system/devpilot.service
install -m 644 "$APP_DIR/deploy/vm/logrotate-devpilot" /etc/logrotate.d/devpilot
echo "17 2 * * * deploy cd $APP_DIR && ./scripts/db-backup.sh >> /var/log/devpilot/backup.log 2>&1" \
  > /etc/cron.d/devpilot-backup && chmod 644 /etc/cron.d/devpilot-backup
systemctl daemon-reload && systemctl enable devpilot

# Firewall: SSH + web only
ufw default deny incoming && ufw default allow outgoing
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp
ufw --force enable

# SSH hardening (drop-in, validated before reload)
cat > /etc/ssh/sshd_config.d/99-devpilot.conf <<'CONF'
PasswordAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
CONF
sshd -t && systemctl reload ssh 2>/dev/null || systemctl reload sshd

dpkg-reconfigure -f noninteractive unattended-upgrades || true

cat <<MSG

Bootstrap complete. Next:
  1. In a NEW terminal confirm:  ssh deploy@<this-vm>
  2. sudo -u deploy nano $APP_DIR/.env   (domain, registry, secrets; see env.prod.example)
  3. Point your DNS A record at this VM, then run the first deploy:
       sudo -u deploy bash -c 'cd $APP_DIR && ./scripts/deploy.sh <image-tag>'
  4. Then: sudo systemctl start devpilot   (keeps the stack up across reboots)
MSG
