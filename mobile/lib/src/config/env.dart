/// Compile-time configuration, supplied with `--dart-define`.
///
/// Production points at the deployed API; local dev/verification points at a
/// locally-run instance of the same FastAPI backend. `devLogin` enables the
/// dev-only sign-in shim (mint a session without the native Google flow), which
/// the web verification build uses since native Google Sign-In can't run there.
class Env {
  Env._();

  /// Base URL of the public API. Defaults to the deployed instance.
  static const apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'https://jobscalper-api.allanweber.dev',
  );

  /// When true, skip native Google Sign-In and post the [devIdToken] stand-in
  /// instead (used by the web verification / screenshot build).
  static const devLogin = bool.fromEnvironment('DEV_LOGIN', defaultValue: false);

  /// A Google ID token stand-in the dev shim posts to `/auth/google`
  /// (the backend's fake verifier accepts `good` in dev/test configs).
  static const devIdToken = String.fromEnvironment('DEV_ID_TOKEN', defaultValue: 'good');

  /// The Google **Web/"server" OAuth client ID**. Passed to Google Sign-In as
  /// `serverClientId` so the returned ID token's audience matches the backend's
  /// `SCALPER_GOOGLE_AUDIENCES`. Supplied at build time via
  /// `--dart-define=GOOGLE_SERVER_CLIENT_ID=...`. Required for real sign-in.
  static const googleServerClientId =
      String.fromEnvironment('GOOGLE_SERVER_CLIENT_ID', defaultValue: '');

  /// The Google **iOS OAuth client ID** (`--dart-define=GOOGLE_IOS_CLIENT_ID=...`).
  /// Only needed for iOS builds; Android derives its client from the registered
  /// package name + signing SHA-1.
  static const googleIosClientId =
      String.fromEnvironment('GOOGLE_IOS_CLIENT_ID', defaultValue: '');

  /// Whether a real Google client is configured for this platform build.
  static bool get hasGoogleConfig =>
      googleServerClientId.isNotEmpty || googleIosClientId.isNotEmpty;
}
