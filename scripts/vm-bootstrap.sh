#!/usr/bin/env bash
# Phase 2: prepare an Ubuntu 22.04/24.04 Linux VM (Azure B2s / AWS t3.medium) to run DevPilot.
set -euo pipefail
sudo apt-get update
sudo apt-get install -y ca-certificates curl git ufw
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp && sudo ufw --force enable
echo "Log out and back in, then: git clone <repo> && ./scripts/dev.sh up"
