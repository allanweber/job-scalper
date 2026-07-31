# Job Scalper — Mobile App (Flutter)

The Android/iOS client for Job Scalper. Reimplements the design handoff natively
in Flutter + Material 3. Built against the public API (`../src/scalper/service`).

## Stack

- **Flutter 3.44**, Material 3.
- **Riverpod** (`Notifier`) for state.
- **go_router** with a `StatefulShellRoute` for the persistent bottom-nav shell
  (Feed / Saved / Applications / Profile), each tab keeping its own stack.
- **dio** HTTP client with bearer injection + single-flight refresh-on-401.
- **shared_preferences** for local persistence (session, onboarding flag, theme).

## Configuration

Compile-time, via `--dart-define`:

| Key | Default | Purpose |
| --- | --- | --- |
| `API_BASE_URL` | `https://jobscalper-api.allanweber.dev` | Public API base URL |
| `DEV_LOGIN` | `false` | Expose the dev sign-in shim (web verification builds) |
| `DEV_ID_TOKEN` | `good` | ID-token stand-in the dev shim posts to `/auth/google` |

Production points at the deployed API. Local dev points at a locally-run instance
of the same FastAPI backend, e.g.:

```
flutter run -d chrome --dart-define=API_BASE_URL=http://localhost:8000 --dart-define=DEV_LOGIN=true
```

## Run / test

```
flutter pub get
flutter analyze
flutter test                 # headless widget tests
```

## Screenshots (no emulator in CI/containers)

There's no Android emulator in the build container, so review screenshots come
from the **web** build driven by headless Chromium at a 390×844 viewport:

```
flutter build web -t lib/main_demo.dart --release --no-web-resources-cdn
python3 tool/screenshots.py     # writes ./screenshots/*.png (light + dark)
```

`lib/main_demo.dart` is a screenshot/QA-only entrypoint that seeds a signed-in
session so the nav shell renders without a backend. `--no-web-resources-cdn`
bundles CanvasKit locally, and Roboto/Roboto Mono are bundled as assets, so the
web build renders fully offline.

## Branding

The brand5 handoff (mint magnifier glyph on brand teal `#006B5E`, mint accent
`#7FF0DD`) is applied across every surface:

- **Launcher / app icons** — Android legacy mipmaps + adaptive icon
  (`mipmap-anydpi-v26` + `ic_launcher_foreground`, teal background via
  `colors.xml`), the full iOS `AppIcon.appiconset` (opaque), and the web
  favicon + PWA icons (standard + maskable, `manifest.json` theme color).
- **Native Android splash** — teal fill with the centered glyph
  (`drawable/launch_background.xml`).
- **In-app** — the glyph and wordmarks ship as assets under `assets/brand/`
  and appear on the Flutter splash and onboarding welcome.

Icons are generated from the source PNGs (no Flutter SDK needed); re-run
`tool/gen_icons.py` if the source art changes.

## Layout

```
lib/
  main.dart                 app entrypoint
  main_demo.dart            screenshot-only entrypoint (pre-seeded session)
  src/
    app.dart                MaterialApp.router + theme wiring
    config/env.dart         compile-time config
    theme/                  design tokens + light/dark ColorScheme
    router/                 go_router + shell + redirect guard
    state/session.dart      session Notifier (auth, onboarding, theme) + TokenStore
    data/                   api client, repositories, wire models
    features/               launch, onboarding, shell (+ per-feature screens)
```
