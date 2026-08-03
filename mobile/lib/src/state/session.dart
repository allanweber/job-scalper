import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../data/api_client.dart';
import '../data/auth_repository.dart';
import '../data/models/api_models.dart';

enum AuthStatus { unknown, signedOut, signedIn }

@immutable
class SessionState {
  const SessionState({
    this.status = AuthStatus.unknown,
    this.user,
    this.tokens,
    this.onboardingComplete = false,
    this.themeMode = ThemeMode.system,
  });

  final AuthStatus status;
  final ApiUser? user;
  final TokenPair? tokens;
  final bool onboardingComplete;
  final ThemeMode themeMode;

  bool get isSignedIn => status == AuthStatus.signedIn;

  SessionState copyWith({
    AuthStatus? status,
    ApiUser? user,
    TokenPair? tokens,
    bool? onboardingComplete,
    ThemeMode? themeMode,
    bool clearAuth = false,
  }) =>
      SessionState(
        status: status ?? this.status,
        user: clearAuth ? null : (user ?? this.user),
        tokens: clearAuth ? null : (tokens ?? this.tokens),
        onboardingComplete: onboardingComplete ?? this.onboardingComplete,
        themeMode: themeMode ?? this.themeMode,
      );
}

/// Owns auth + persisted app-level flags, and backs the API client's [TokenStore].
class SessionController extends Notifier<SessionState> implements TokenStore {
  late final ApiClient api = ApiClient(this);
  late final AuthRepository _auth = AuthRepository(api);

  SharedPreferences get _prefs => ref.read(sharedPrefsProvider);

  static const _kTokens = 'session.tokens';
  static const _kOnboarding = 'session.onboardingComplete';
  static const _kTheme = 'session.themeMode';

  @override
  SessionState build() {
    final onboarding = _prefs.getBool(_kOnboarding) ?? false;
    final theme = ThemeMode.values[_prefs.getInt(_kTheme) ?? ThemeMode.system.index];
    final raw = _prefs.getString(_kTokens);
    final tokens = raw == null
        ? null
        : TokenPair.fromJson(jsonDecode(raw) as Map<String, dynamic>);
    return SessionState(
      status: tokens == null ? AuthStatus.signedOut : AuthStatus.signedIn,
      tokens: tokens,
      onboardingComplete: onboarding,
      themeMode: theme,
    );
  }

  Future<void> signInWithGoogle(String idToken) async {
    final res = await _auth.signInWithGoogle(idToken);
    await _persistTokens(res.tokens);
    state = state.copyWith(
        status: AuthStatus.signedIn, user: res.user, tokens: res.tokens);
  }

  Future<void> signOut() async {
    final rt = state.tokens?.refreshToken;
    if (rt != null) {
      try {
        await _auth.logout(rt);
      } catch (_) {/* best-effort */}
    }
    await _prefs.remove(_kTokens);
    state = state.copyWith(status: AuthStatus.signedOut, clearAuth: true);
  }

  /// Replace the cached user (e.g. after accepting legal terms mid-onboarding).
  void updateUser(ApiUser user) => state = state.copyWith(user: user);

  /// Hydrate the cached user from the server. A restored session persists only
  /// the token pair, so [user] starts null on relaunch; call this once at launch
  /// so the profile header and footer show real details instead of placeholders.
  /// Best-effort: a transient failure leaves the session as-is, while a hard
  /// auth failure is handled by the client's 401 interceptor.
  Future<void> refreshUser() async {
    if (!state.isSignedIn) return;
    try {
      final user = await _auth.me();
      state = state.copyWith(user: user);
    } catch (_) {/* best-effort; keep the existing session */}
  }

  Future<void> completeOnboarding() async {
    await _prefs.setBool(_kOnboarding, true);
    state = state.copyWith(onboardingComplete: true);
  }

  /// Replay onboarding without clearing the user's data.
  Future<void> resetOnboarding() async {
    await _prefs.setBool(_kOnboarding, false);
    state = state.copyWith(onboardingComplete: false);
  }

  Future<void> setThemeMode(ThemeMode mode) async {
    await _prefs.setInt(_kTheme, mode.index);
    state = state.copyWith(themeMode: mode);
  }

  Future<void> _persistTokens(TokenPair t) =>
      _prefs.setString(_kTokens, jsonEncode(t.toJson()));

  // -- TokenStore --
  @override
  String? get accessToken => state.tokens?.accessToken;

  @override
  String? get refreshToken => state.tokens?.refreshToken;

  @override
  Future<void> onTokensRefreshed(String access, String refresh) async {
    final t = TokenPair(
        accessToken: access, refreshToken: refresh, expiresIn: state.tokens?.expiresIn ?? 900);
    await _persistTokens(t);
    state = state.copyWith(tokens: t);
  }

  @override
  Future<void> onAuthLost() async {
    await _prefs.remove(_kTokens);
    state = state.copyWith(status: AuthStatus.signedOut, clearAuth: true);
  }
}

/// Overridden in `main()` once SharedPreferences is loaded.
final sharedPrefsProvider = Provider<SharedPreferences>(
    (ref) => throw UnimplementedError('sharedPrefsProvider must be overridden'));

final sessionProvider =
    NotifierProvider<SessionController, SessionState>(SessionController.new);
