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

## Google Sign-In setup

Sign-in uses native Google Sign-In (`google_sign_in`) to obtain a Google **ID
token**, which the app posts to `POST /auth/google`. Getting it working end to
end requires configuration in three places.

### 1. Google Cloud OAuth clients (you create these)

In the Google Cloud console (APIs & Services → Credentials), create OAuth client
IDs for your project:

- **Web application** client — this is the *server/audience* client. Its client
  ID is what the app passes as `serverClientId` and what the backend must accept
  as an audience. **Required for Android and iOS** (it's what makes the returned
  ID token's `aud` match the backend).
- **Android** client — enter the package name `dev.allanweber.job_scalper` and
  the SHA-1 of your signing key. Add **two**: the SHA-1 of your upload keystore,
  and (if you use Play App Signing) the SHA-1 Google shows under App Signing.
  Get your upload SHA-1 with:
  `keytool -list -v -keystore upload-keystore.jks -alias upload`
- **iOS** client (only for iOS builds) — enter the bundle ID. Copy its
  *reversed* client ID into `ios/Runner/Info.plist` (replace
  `REPLACE_WITH_REVERSED_IOS_CLIENT_ID`).

### 2. Build-time config (client IDs are not secrets, but injected at build)

| dart-define | Value |
| --- | --- |
| `GOOGLE_SERVER_CLIENT_ID` | the **Web** client ID (ends in `.apps.googleusercontent.com`) |
| `GOOGLE_IOS_CLIENT_ID` | the **iOS** client ID (iOS builds only) |

CI passes `GOOGLE_SERVER_CLIENT_ID` from the repo secret of the same name into
the release APK. Set it under **Settings → Secrets and variables → Actions**.
Local run:

```
flutter run --dart-define=GOOGLE_SERVER_CLIENT_ID=<web-client-id>.apps.googleusercontent.com
```

### 3. Backend (your Dokploy deployment)

- Install the API with the `.[api]` extra (the Dockerfile already does; the
  current 500 on `/auth/google` means the **deployed image is stale** — redeploy
  from latest so `google-auth` is present).
- Set `SCALPER_GOOGLE_AUDIENCES` to the **Web** client ID (comma-separated if you
  accept more than one). The ID token's `aud` must be in this list.

Until real clients are configured, the **web verification build** uses a dev
shim (`--dart-define=DEV_LOGIN=true`) that skips native Google and posts the
`DEV_ID_TOKEN` stand-in, which a dev/test backend accepts.

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
