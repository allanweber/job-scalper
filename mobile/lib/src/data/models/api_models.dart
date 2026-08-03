/// Wire models mirroring the FastAPI schemas (`scalper/service/schemas.py`).
///
/// Hand-written for now; the plan is to regenerate these from the OpenAPI spec
/// as the surface grows. Only the fields the app reads are modelled.
class TokenPair {
  const TokenPair({
    required this.accessToken,
    required this.refreshToken,
    required this.expiresIn,
  });

  final String accessToken;
  final String refreshToken;
  final int expiresIn;

  factory TokenPair.fromJson(Map<String, dynamic> j) => TokenPair(
        accessToken: j['access_token'] as String,
        refreshToken: j['refresh_token'] as String,
        expiresIn: (j['expires_in'] as num?)?.toInt() ?? 900,
      );

  Map<String, dynamic> toJson() => {
        'access_token': accessToken,
        'refresh_token': refreshToken,
        'expires_in': expiresIn,
      };
}

class ApiUser {
  const ApiUser({
    required this.id,
    required this.email,
    this.displayName,
    this.avatarUrl,
    required this.plan,
    required this.tosAccepted,
    required this.privacyAccepted,
    this.hasProfile = false,
  });

  final String id;
  final String email;
  final String? displayName;
  final String? avatarUrl;
  final String plan;
  final bool tosAccepted;
  final bool privacyAccepted;

  /// Whether the account has a saved search profile — the server's answer to
  /// "has this account finished onboarding", used to gate the onboarding flow
  /// independent of any device-local flag.
  final bool hasProfile;

  bool get legalAccepted => tosAccepted && privacyAccepted;

  factory ApiUser.fromJson(Map<String, dynamic> j) => ApiUser(
        id: j['id'] as String,
        email: j['email'] as String,
        displayName: j['display_name'] as String?,
        avatarUrl: j['avatar_url'] as String?,
        plan: (j['plan'] as String?) ?? 'free',
        tosAccepted: (j['tos_accepted'] as bool?) ?? false,
        privacyAccepted: (j['privacy_accepted'] as bool?) ?? false,
        hasProfile: (j['has_profile'] as bool?) ?? false,
      );
}
