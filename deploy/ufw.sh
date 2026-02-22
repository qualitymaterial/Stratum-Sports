#!/usr/bin/env bash
set -euo pipefail

APP_PORT="${APP_PORT:-8000}"

sudo ufw --force reset
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow "${APP_PORT}/tcp"
sudo ufw --force enable
sudo ufw status verbose
