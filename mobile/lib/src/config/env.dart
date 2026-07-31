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

  /// When true, expose the dev sign-in shim on the auth screen.
  static const devLogin = bool.fromEnvironment('DEV_LOGIN', defaultValue: false);

  /// A Google ID token stand-in the dev shim posts to `/auth/google`
  /// (the backend's fake verifier accepts `good` in dev/test configs).
  static const devIdToken = String.fromEnvironment('DEV_ID_TOKEN', defaultValue: 'good');
}
