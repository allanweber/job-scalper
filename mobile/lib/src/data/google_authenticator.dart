import 'package:google_sign_in/google_sign_in.dart';

import '../config/env.dart';

/// Obtains a Google ID token to exchange for an app session at
/// `POST /auth/google`. Declared as an interface so widget tests and the
/// screenshot harness inject a fake instead of touching the platform.
abstract class GoogleAuthenticator {
  /// Returns a Google ID token, or `null` if the user cancelled the flow.
  /// Throws with a human-readable message on a real failure.
  Future<String?> obtainIdToken();

  /// Fully disconnect the Google account, revoking the link so a later sign-in
  /// needs a fresh, explicit consent. Best-effort. Called on account deletion:
  /// without it the next "Sign in with Google" silently re-authenticates the
  /// same account and the backend creates a new one, making the deletion look
  /// like it never happened.
  Future<void> disconnect();
}

/// Real native Google Sign-In (Android/iOS). Needs OAuth client IDs configured
/// in Google Cloud and supplied at build time (see [Env]); Android additionally
/// requires the app's package name + signing SHA-1 registered on an Android
/// OAuth client.
class GoogleSignInAuthenticator implements GoogleAuthenticator {
  bool _initialized = false;

  Future<void> _ensureInit() async {
    if (_initialized) return;
    await GoogleSignIn.instance.initialize(
      serverClientId:
          Env.googleServerClientId.isEmpty ? null : Env.googleServerClientId,
      clientId: Env.googleIosClientId.isEmpty ? null : Env.googleIosClientId,
    );
    _initialized = true;
  }

  @override
  Future<String?> obtainIdToken() async {
    await _ensureInit();
    if (!GoogleSignIn.instance.supportsAuthenticate()) {
      throw Exception('Google Sign-In is not supported on this platform.');
    }
    try {
      final account = await GoogleSignIn.instance.authenticate();
      final idToken = account.authentication.idToken;
      if (idToken == null || idToken.isEmpty) {
        throw Exception(
            'Google returned no ID token — check that GOOGLE_SERVER_CLIENT_ID '
            'is set to your Web client ID.');
      }
      return idToken;
    } on GoogleSignInException catch (e) {
      if (e.code == GoogleSignInExceptionCode.canceled) return null;
      final detail = e.description == null ? '' : ' — ${e.description}';
      throw Exception('Google Sign-In failed (${e.code.name})$detail');
    }
  }

  @override
  Future<void> disconnect() async {
    await _ensureInit();
    await GoogleSignIn.instance.disconnect();
  }
}

/// Dev stand-in for the web verification / screenshot build (`DEV_LOGIN=true`):
/// returns the configured dev id-token so the flow works without native Google.
class DevGoogleAuthenticator implements GoogleAuthenticator {
  @override
  Future<String?> obtainIdToken() async => Env.devIdToken;

  @override
  Future<void> disconnect() async {/* no native session to disconnect */}
}
