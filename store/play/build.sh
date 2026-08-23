#!/usr/bin/env bash
# Regenerate the Play Store visual assets from source and collect them for upload.
#
#   ./store/play/build.sh
#
# Produces store/play/out/ containing the feature graphic, the 512 icon, and a
# representative set of phone screenshots. Re-run it whenever the brand or the
# app UI changes. Needs a Chrome/Chromium to render the feature graphic; it
# finds the Playwright Chromium automatically, or set CHROME=/path/to/chrome.
#
# Note: feature-graphic.html links the brand webfonts (Inter / Space Grotesk).
# With network they render; offline (e.g. a sandbox) it falls back to the system
# sans-serif, which still looks clean — regenerate online for the final upload.
set -euo pipefail
cd "$(dirname "$0")"

CHROME="${CHROME:-}"
if [ -z "$CHROME" ]; then
  for c in "${PLAYWRIGHT_BROWSERS_PATH:-}/chromium" /opt/pw-browsers/chromium \
           "$(command -v google-chrome || true)" "$(command -v chromium || true)" \
           "$(command -v chromium-browser || true)"; do
    if [ -n "$c" ] && [ -x "$c" ]; then CHROME="$c"; break; fi
  done
fi
[ -z "$CHROME" ] && { echo "No Chrome/Chromium found; set CHROME=/path/to/chrome" >&2; exit 1; }

echo "Rendering feature-graphic.png (1024x500) with $CHROME"
"$CHROME" --headless=new --no-sandbox --hide-scrollbars --force-device-scale-factor=1 \
  --window-size=1024,500 --virtual-time-budget=3000 \
  --screenshot=feature-graphic.png "file://$PWD/feature-graphic.html"

mkdir -p out
cp feature-graphic.png out/
cp ../../mobile/brand_src/icon-square-512-play.png out/icon-512.png 2>/dev/null || \
  echo "  (icon-square-512-play.png not found; skipping)"

# Phone screenshots: the committed portfolio captures are phone-viewport PNGs,
# which double as Play phone screenshots. Pick a representative set (light theme).
count=0
for n in feed job-detail applications insights draft-detail profile; do
  f="../../portfolio/images/${n}-light.png"
  if [ -f "$f" ]; then
    count=$((count + 1))
    cp "$f" "$(printf 'out/screenshot-%02d-%s.png' "$count" "$n")"
  fi
done
[ "$count" = 0 ] && echo "  (no portfolio screenshots found; run mobile/tool/portfolio_shots.py first)"

echo "Assets ready in $PWD/out:"
ls -1 out
