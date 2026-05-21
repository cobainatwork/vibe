#!/usr/bin/env bash
set -euo pipefail

errors=0
warn() { echo "  ⚠️  $*"; errors=$((errors+1)); }
ok()   { echo "  ✅ $*"; }

echo "Preflight checks:"

# Docker
if command -v docker >/dev/null; then
    ok "docker $(docker --version | awk '{print $3}')"
else
    warn "docker not found"
fi

# GPU
if command -v nvidia-smi >/dev/null; then
    cc=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader | head -1 | tr -d ' ')
    vram=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
    ok "GPU compute capability $cc, VRAM ${vram} MB"
    cc_num=${cc//./}
    if [ "$cc_num" -lt "80" ]; then
        warn "GPU compute capability < 8.0 (Ampere); flash_attention_2 won't work"
    fi
    if [ "$vram" -lt "24000" ]; then
        warn "VRAM < 24GB; may OOM"
    fi
else
    warn "nvidia-smi not found"
fi

# Files
[ -f config/api_keys.yaml ] && ok "api_keys.yaml present" || warn "config/api_keys.yaml missing"
[ -f .env ] && ok ".env present" || warn ".env missing"
[ -d current_model ] && [ -n "$(ls -A current_model)" ] && ok "current_model populated" || warn "current_model empty"
[ -d vibevoice_src ] && ok "vibevoice_src cloned" || warn "vibevoice_src missing — run scripts/clone_upstream.sh"

# Disk
free_gb=$(df -BG . | awk 'NR==2 {gsub("G","",$4); print $4}')
if [ "$free_gb" -lt 50 ]; then
    warn "free disk < 50GB ($free_gb GB)"
else
    ok "free disk ${free_gb}GB"
fi

if [ $errors -gt 0 ]; then
    echo "$errors check(s) failed."
    exit 1
fi
echo "All preflight checks passed."
