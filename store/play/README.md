# Play Store listing assets (PLAY-7)

Everything visual the Play listing needs, regenerated from source with one
command. The listing **text** (name, descriptions, category, content rating,
data safety) lives in [`docs/play/registration.md`](../../docs/play/registration.md).

## Regenerate

```bash
./store/play/build.sh
```

Renders the feature graphic and collects the upload set into `store/play/out/`
(gitignored). Needs a Chrome/Chromium — it finds the Playwright one
automatically, or set `CHROME=/path/to/chrome`.

## Assets

| Asset | Spec (Play) | Source | Status |
| --- | --- | --- | --- |
| **App icon** | 512×512 PNG, 32-bit | `mobile/brand_src/icon-square-512-play.png` | ✅ committed |
| **Feature graphic** | 1024×500 PNG/JPEG | `feature-graphic.html` → `feature-graphic.png` | ✅ committed |
| **Phone screenshots** | 2–8, ≥320 px, portrait | `portfolio/images/*-light.png` (from `mobile/tool/portfolio_shots.py`) | ✅ generated |
| Tablet screenshots | only if you declare tablet support | `portfolio_shots.py` at a tablet viewport | ⬜ optional |

### Feature graphic

`feature-graphic.png` is the committed asset (upload this). To restyle, edit
`feature-graphic.html` and re-run `build.sh`. The design links the brand
webfonts (Inter / Space Grotesk); with network they render, offline it falls
back to the system sans-serif — **regenerate on a networked machine for the
final upload** so the typography matches the brand.

### Screenshots

The committed portfolio captures are phone-viewport PNGs that double as Play
phone screenshots. `build.sh` copies a representative light-theme set
(feed → job detail → applications → insights → draft → profile). To refresh
them from the current app UI:

```bash
cd mobile && flutter build web --target=lib/main_portfolio.dart && \
  python tool/portfolio_shots.py
```

## Upload checklist

1. `./store/play/build.sh` (on a networked machine).
2. Upload `out/feature-graphic.png`, `out/icon-512.png`, and the `out/screenshot-*.png` set.
3. Fill the listing text + declarations from `docs/play/registration.md`.
