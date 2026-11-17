#!/usr/bin/env bash
# Enter the free-trial AI keys into the production settings file (docs/runbooks/RELEASE_0.11.05.md, step 3).
# Run by the OWNER on the server, as the user that owns the file:
#   sudo -u deploy -H bash enter_trial_ai_keys.sh [settings file]     (default /home/deploy/mdarix/.env.production)
# Asks for the FreeLLMAPI and OmniRoute access keys (each gateway's own key, created in its dashboard) and the Groq
# key, without echo. An empty answer keeps the value already in the file. Also sets the trial chain, the platform
# feature list and OmniRoute's combo. Values are never printed: each setting reports only "set" or "unchanged".
# The file is replaced atomically (mode 600) after a timestamped copy of it is kept beside it (mode 600).
set -euo pipefail
umask 077

FILE="${1:-/home/deploy/mdarix/.env.production}"
[ -f "$FILE" ] || { echo "STOP: $FILE not found; nothing was changed." >&2; exit 1; }
[ -w "$FILE" ] || { echo "STOP: $FILE is not writable by $(id -un); run as its owner (sudo -u deploy -H ...)." >&2; exit 1; }

# The offered features of genai/features.py (decision_advisory and regulatory_drafting are not offered).
FEATURES="ask,summaries,case_analysis,drafting,evidence_extraction,code_suggestions"
CHAIN="freellmapi,omniroute,groq"
OMNIROUTE_COMBO="mdarix-trial"

# Compose reads the file as KEY=value: no quotes, no spaces, no "$" (it would be interpolated) and no "#".
valid() { [[ "$1" =~ ^[A-Za-z0-9._~+/=:-]+$ ]]; }

ask_key() { # $1 prompt; the answer goes to REPLY_KEY
  local answer=""
  read -r -s -p "$1 (empty = keep the current value): " answer || true
  echo >&2
  if [ -n "$answer" ] && ! valid "$answer"; then
    echo "STOP: that key has a character the settings file cannot hold as is (space, quote, \$ or #); nothing was changed." >&2
    exit 1
  fi
  REPLY_KEY="$answer"
}

declare -a NAMES=() VALUES=()
add() { NAMES+=("$1"); VALUES+=("$2"); }

ask_key "FreeLLMAPI access key"
[ -n "$REPLY_KEY" ] && add MDARIX_GENAI_FREELLMAPI_API_KEY "$REPLY_KEY"
ask_key "OmniRoute access key"
[ -n "$REPLY_KEY" ] && add MDARIX_GENAI_OMNIROUTE_API_KEY "$REPLY_KEY"
ask_key "Groq API key"
[ -n "$REPLY_KEY" ] && add MDARIX_GENAI_GROQ_API_KEY "$REPLY_KEY"
add MDARIX_GENAI_OMNIROUTE_MODEL "$OMNIROUTE_COMBO"
add MDARIX_AI_TRIAL_CHAIN "$CHAIN"
add MDARIX_AI_FEATURES "$FEATURES"

DIR=$(dirname "$FILE")
TMP=$(mktemp "$DIR/.trial-ai-keys.XXXXXX")
trap 'rm -f "$TMP"' EXIT
cp "$FILE" "$TMP"

declare -a REPORT=()
changed=0
for i in "${!NAMES[@]}"; do
  name="${NAMES[$i]}"
  # The last KEY= line wins in an env file; compare with it.
  current=$(grep -E "^${name}=" "$TMP" | tail -n 1 | cut -d= -f2- || true)
  if [ "$(grep -cE "^${name}=" "$TMP" || true)" = "1" ] && [ "$current" = "${VALUES[$i]}" ]; then
    REPORT+=("$name: unchanged")
    continue
  fi
  # Value passed through the environment (awk -v would expand backslashes); one line, duplicates dropped.
  NAME="$name" VALUE="${VALUES[$i]}" awk '
    BEGIN { prefix = ENVIRON["NAME"] "=" }
    index($0, prefix) == 1 { if (!done) { print prefix ENVIRON["VALUE"]; done = 1 } next }
    { print }
    END { if (!done) print prefix ENVIRON["VALUE"] }
  ' "$TMP" > "$TMP.new"
  mv "$TMP.new" "$TMP"
  REPORT+=("$name: set")
  changed=1
done

if [ "$changed" -eq 1 ]; then
  BACKUP="$FILE.pre-trial-ai-$(date -u +%Y%m%dT%H%M%SZ)"
  cp -p "$FILE" "$BACKUP"
  chmod 600 "$BACKUP"
  chmod 600 "$TMP"
  mv -f "$TMP" "$FILE"
  echo "Previous file kept as $BACKUP"
fi
printf '%s\n' "${REPORT[@]}"
[ "$changed" -eq 1 ] && echo "The services read the file when they are recreated: docker compose up -d --no-build --wait" || true
