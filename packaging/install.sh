#!/usr/bin/env bash
# bus-mcp installer.
#
# Idempotent — re-runs cleanly. Does as much of the setup as a single
# command can without making destructive choices on your behalf:
#
#   1. Picks an install prefix (default ~/.local/share/bus-mcp/.venv)
#   2. Creates a venv with --system-site-packages so existing
#      apt-packaged lgpio / spidev / smbus2 work without rebuilding
#   3. Installs `bus-mcp` itself, `mcp`, and `python-can`
#   4. Adds the install user to spi / i2c / gpio / dialout groups so
#      the buses are reachable without sudo
#   5. Generates /etc/systemd/system/bus-mcp.service from the template
#      and enables + starts it
#
# What it does NOT do (these are physical / boot-time choices):
#   - Edit /boot/firmware/config.txt or load CAN HAT overlays
#     (different HAT variants need different pinouts — see README)
#   - Pick a CAN bitrate — your `robodaqc-can.service` or
#     `ip link set canX up type can bitrate <N>` does that
#   - Punch firewall holes — the server binds 0.0.0.0:7820 by default,
#     fence with ufw/iptables if exposing beyond your LAN
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/.../install.sh | bash
#   # or, after cloning:
#   ./packaging/install.sh [options]
#
# Options:
#   --prefix PATH     venv root (default ~/.local/share/bus-mcp/.venv)
#   --user NAME       systemd unit User= (default $USER)
#   --port N          HTTP port (default 7820)
#   --host ADDR       HTTP bind host (default 0.0.0.0)
#   --allow-write     enable write tools by default
#   --no-systemd      skip the systemd unit install
#   --no-groups       skip the supplementary-group additions
#   --source DIR      install from this local checkout instead of PyPI
#                     (default: detected if you run the script from a clone)
#   --uninstall       tear down (disable unit, remove venv, leave groups)

set -euo pipefail

# ── defaults ──────────────────────────────────────────────────────────
PREFIX="${HOME}/.local/share/bus-mcp"
TARGET_USER="${USER}"
PORT="7820"
HOST="0.0.0.0"
ALLOW_WRITE=""
INSTALL_SYSTEMD=1
INSTALL_GROUPS=1
SOURCE_DIR=""
UNINSTALL=0

# ── arg parse ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix) PREFIX="$2"; shift 2 ;;
    --user) TARGET_USER="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --host) HOST="$2"; shift 2 ;;
    --allow-write) ALLOW_WRITE="--allow-write"; shift ;;
    --no-systemd) INSTALL_SYSTEMD=0; shift ;;
    --no-groups) INSTALL_GROUPS=0; shift ;;
    --source) SOURCE_DIR="$2"; shift 2 ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help)
      sed -n '/^# Usage/,/^# Options/p' "$0" | sed 's/^# \{0,1\}//' ; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

VENV="${PREFIX}/.venv"
UNIT_FILE="/etc/systemd/system/bus-mcp.service"

# Auto-detect source dir when run from a checkout.
if [[ -z "${SOURCE_DIR}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
  if [[ -f "${SCRIPT_DIR}/../pyproject.toml" ]]; then
    SOURCE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
  fi
fi

log()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m   ok\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m   ⚠\033[0m  %s\n' "$*"; }
err()  { printf '\033[1;31m   ✗\033[0m  %s\n' "$*" >&2; }

need() { command -v "$1" >/dev/null || { err "missing dependency: $1"; exit 1; }; }

# ── uninstall ─────────────────────────────────────────────────────────
if [[ $UNINSTALL -eq 1 ]]; then
  log "Uninstalling bus-mcp"
  if [[ -f "$UNIT_FILE" ]]; then
    sudo systemctl disable --now bus-mcp.service 2>/dev/null || true
    sudo rm -f "$UNIT_FILE"
    sudo systemctl daemon-reload
    ok "systemd unit removed"
  fi
  if [[ -d "$VENV" ]]; then
    rm -rf "$VENV"
    ok "venv removed: $VENV"
  fi
  warn "Group memberships (spi/i2c/gpio/dialout) left untouched"
  exit 0
fi

# ── preflight ─────────────────────────────────────────────────────────
log "Preflight"
need python3
PYV=$(python3 -c 'import sys; print("%d.%d"%sys.version_info[:2])')
case "$PYV" in
  3.11|3.12|3.13|3.14) ok "python3 $PYV" ;;
  *) err "bus-mcp requires Python ≥ 3.11 (found $PYV)"; exit 1 ;;
esac

if [[ -r /proc/device-tree/model ]]; then
  MODEL=$(tr -d '\0' < /proc/device-tree/model)
  ok "host model: ${MODEL}"
else
  warn "not a Raspberry Pi — hardware tools will fail, but the server still installs"
fi

# ── groups ────────────────────────────────────────────────────────────
if [[ $INSTALL_GROUPS -eq 1 ]]; then
  log "Adding ${TARGET_USER} to spi / i2c / gpio / dialout"
  added=0
  for g in spi i2c gpio dialout; do
    if getent group "$g" >/dev/null; then
      if id -nG "$TARGET_USER" | tr ' ' '\n' | grep -qx "$g"; then
        : # already a member
      else
        sudo usermod -aG "$g" "$TARGET_USER"
        added=$((added+1))
      fi
    fi
  done
  if [[ $added -gt 0 ]]; then
    warn "${TARGET_USER} added to ${added} group(s) — log out + back in (or reboot) so the new groups take effect"
  else
    ok "${TARGET_USER} already in all needed groups"
  fi
fi

# ── venv + python deps ────────────────────────────────────────────────
log "Creating venv at ${VENV}"
mkdir -p "$PREFIX"
if [[ ! -d "$VENV" ]]; then
  python3 -m venv --system-site-packages "$VENV"
  ok "venv created"
else
  ok "venv exists — reusing"
fi
"$VENV/bin/pip" install -q --upgrade pip
ok "pip upgraded"

log "Installing python-can + mcp"
"$VENV/bin/pip" install -q "mcp>=1.0" "python-can>=4.3"
ok "core deps installed"

log "Installing bus-mcp"
if [[ -n "$SOURCE_DIR" && -f "${SOURCE_DIR}/pyproject.toml" ]]; then
  "$VENV/bin/pip" install -q --no-deps -e "$SOURCE_DIR"
  ok "bus-mcp installed (editable from $SOURCE_DIR)"
else
  "$VENV/bin/pip" install -q --no-deps "bus-mcp"
  ok "bus-mcp installed from PyPI"
fi

# Sanity check the CLI before wiring systemd.
if ! "$VENV/bin/bus-mcp" --version >/dev/null 2>&1; then
  err "bus-mcp CLI failed to launch — abort"
  exit 1
fi
ok "$(${VENV}/bin/bus-mcp --version)"

# ── systemd unit ──────────────────────────────────────────────────────
if [[ $INSTALL_SYSTEMD -eq 1 ]]; then
  log "Installing systemd unit at ${UNIT_FILE}"
  TEMPLATE="${SOURCE_DIR}/packaging/systemd/bus-mcp.service.in"
  if [[ ! -f "$TEMPLATE" ]]; then
    err "missing template at $TEMPLATE (re-run from a bus-mcp checkout)"
    exit 1
  fi
  TMP=$(mktemp)
  sed -e "s|@USER@|${TARGET_USER}|g" \
      -e "s|@GROUP@|${TARGET_USER}|g" \
      -e "s|@VENV_BIN@|${VENV}/bin|g" \
      -e "s|@HOST@|${HOST}|g" \
      -e "s|@PORT@|${PORT}|g" \
      -e "s|@ALLOW_WRITE@|${ALLOW_WRITE}|g" \
      "$TEMPLATE" > "$TMP"
  sudo install -m 0644 "$TMP" "$UNIT_FILE"
  rm -f "$TMP"
  sudo systemctl daemon-reload
  sudo systemctl enable --now bus-mcp.service
  sleep 1
  if systemctl is-active --quiet bus-mcp.service; then
    ok "bus-mcp.service active"
  else
    err "bus-mcp.service failed to start — see: sudo journalctl -u bus-mcp -n 50"
    exit 1
  fi
fi

# ── final report ──────────────────────────────────────────────────────
log "Discovered buses on this host:"
"$VENV/bin/bus-mcp" list 2>&1 | sed 's/^/    /' | head -30

cat <<EOF

────────────────────────────────────────────────────────────
 bus-mcp is up.

 MCP endpoint   : http://${HOST}:${PORT}/mcp
 Write enabled  : $( [[ -n "$ALLOW_WRITE" ]] && echo "yes" || echo "no" )
 Venv           : ${VENV}
 Systemd unit   : $( [[ $INSTALL_SYSTEMD -eq 1 ]] && echo "bus-mcp.service" || echo "(skipped)" )

 Wire into Claude Code:
   claude mcp add --transport http bus-mcp http://$(hostname -I | awk '{print $1}'):${PORT}/mcp

 Logs:
   sudo journalctl -u bus-mcp -f

 Uninstall:
   ./install.sh --uninstall
────────────────────────────────────────────────────────────
EOF
