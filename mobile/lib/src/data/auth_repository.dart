import 'api_client.dart';
import 'models/api_models.dart';

/// Sign-in / session endpoints (`/auth/*`, `/me`).
///
/// `signInWithGoogle` posts a Google ID token (a real one on device, or the dev
/// shim's stand-in on the web verification build) and receives the app's own
/// JWT pair. Repositories, not screens, own the wire shapes.
class AuthRepository {
  AuthRepository(this._api);

  final ApiClient _api;

  Future<({ApiUser user, TokenPair tokens})> signInWithGoogle(
      String idToken) async {
    final r = await _api.post<Map<String, dynamic>>('/auth/google',
        data: {'id_token': idToken}, noAuth: true);
    final data = r.data!;
    return (
      user: ApiUser.fromJson(data['user'] as Map<String, dynamic>),
      tokens: TokenPair.fromJson(data['tokens'] as Map<String, dynamic>),
    );
  }

  Future<ApiUser> me() async {
    final r = await _api.get<Map<String, dynamic>>('/me');
    return ApiUser.fromJson(r.data!);
  }

  Future<void> logout(String refreshToken) async {
    await _api.post<Map<String, dynamic>>('/auth/logout',
        data: {'refresh_token': refreshToken}, noAuth: true);
  }
}
