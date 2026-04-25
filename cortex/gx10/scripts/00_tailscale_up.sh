#!/usr/bin/env bash
# Bring Tailscale up on the GX10. Run after reboot or before each demo session.
# PRD §3 (transport) + §13-R3 (venue Wi-Fi mitigation).
# Verify with `tailscale ip -4` and from laptop: curl http://<gx10-ip>:8080/health
set -euo pipefail

if ! command -v tailscale >/dev/null 2>&1; then
  echo "tailscale not installed. install per https://tailscale.com/download" >&2
  exit 1
fi

sudo tailscale up
tailscale ip -4
