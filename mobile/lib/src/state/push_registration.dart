import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../data/providers.dart';
import 'session.dart';

/// Keeps this device's FCM token registered with the backend for as long as the
/// user is signed in. Registers on sign-in (and at startup if already signed
/// in), re-registers when FCM rotates the token, and exposes an explicit
/// unregister for the sign-out flow to call before the session drops its tokens.
///
/// Everything is best-effort: with Firebase unavailable the messaging layer is a
/// no-op, so this quietly does nothing (tests, iOS before APNs setup, etc.).
class PushRegistration extends Notifier<void> {
  String? _token;
  StreamSubscription<String>? _refreshSub;

  @override
  void build() {
    ref.onDispose(() {
      _refreshSub?.cancel();
    });
    ref.listen(sessionProvider, (prev, next) {
      final was = prev?.isSignedIn ?? false;
      if (next.isSignedIn && !was) {
        unawaited(_register());
      }
    });
    if (ref.read(sessionProvider).isSignedIn) {
      Future.microtask(_register);
    }
  }

  Future<void> _register() async {
    final msg = ref.read(pushMessagingProvider);
    try {
      if (!await msg.requestPermission()) return;
      final token = await msg.getToken();
      if (token == null) return;
      _token = token;
      await ref
          .read(accountRepositoryProvider)
          .registerDevice(token, platform: msg.platform);
      _refreshSub ??= msg.onTokenRefresh.listen((t) async {
        _token = t;
        try {
          await ref
              .read(accountRepositoryProvider)
              .registerDevice(t, platform: msg.platform);
        } catch (_) {/* best-effort */}
      });
    } catch (_) {/* best-effort — never block the app on push */}
  }

  /// Remove this device's token server-side. Call this from the sign-out flow
  /// *before* the session clears its tokens, so the request is still authorized.
  Future<void> unregisterCurrent() async {
    final token = _token;
    _token = null;
    await _refreshSub?.cancel();
    _refreshSub = null;
    if (token == null) return;
    try {
      await ref.read(accountRepositoryProvider).unregisterDevice(token);
    } catch (_) {/* best-effort */}
  }
}

final pushRegistrationProvider =
    NotifierProvider<PushRegistration, void>(PushRegistration.new);
