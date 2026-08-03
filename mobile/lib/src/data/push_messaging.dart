import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';

/// Set true by `main()` only after `Firebase.initializeApp()` succeeds. Guards
/// every access to the FCM plugin so tests (and any platform without Firebase
/// configured, e.g. iOS before its APNs setup) transparently use the no-op
/// messaging and never touch the native channel.
bool firebaseAvailable = false;

/// A notification the user tapped to open the app, carrying the posting it was
/// about (for deep-linking).
class PushOpen {
  const PushOpen({this.postingId});
  final String? postingId;
}

/// Thin abstraction over FCM so device-token registration doesn't leak the
/// plugin into the rest of the app or the tests. [FirebasePushMessaging] talks
/// to firebase_messaging; [NoopPushMessaging] is used everywhere Firebase isn't
/// available.
abstract class PushMessaging {
  /// Ask the OS for notification permission (Android 13+ prompts; older Android
  /// auto-grants). Returns true when notifications are allowed.
  Future<bool> requestPermission();

  /// The device's current FCM registration token, or null if unavailable.
  Future<String?> getToken();

  /// Emits a new token whenever FCM rotates it.
  Stream<String> get onTokenRefresh;

  /// Notification taps that brought the app to the foreground.
  Stream<PushOpen> get onOpened;

  /// The notification that cold-launched the app, if any.
  Future<PushOpen?> initialOpen();

  /// Platform tag stored with the token ('android' | 'ios'), or null.
  String? get platform;
}

class NoopPushMessaging implements PushMessaging {
  const NoopPushMessaging();
  @override
  Future<bool> requestPermission() async => false;
  @override
  Future<String?> getToken() async => null;
  @override
  Stream<String> get onTokenRefresh => const Stream.empty();
  @override
  Stream<PushOpen> get onOpened => const Stream.empty();
  @override
  Future<PushOpen?> initialOpen() async => null;
  @override
  String? get platform => null;
}

class FirebasePushMessaging implements PushMessaging {
  FirebasePushMessaging(this._fm);
  final FirebaseMessaging _fm;

  @override
  Future<bool> requestPermission() async {
    final s = await _fm.requestPermission();
    return s.authorizationStatus == AuthorizationStatus.authorized ||
        s.authorizationStatus == AuthorizationStatus.provisional;
  }

  @override
  Future<String?> getToken() => _fm.getToken();

  @override
  Stream<String> get onTokenRefresh => _fm.onTokenRefresh;

  @override
  Stream<PushOpen> get onOpened =>
      FirebaseMessaging.onMessageOpenedApp.map(_toOpen);

  @override
  Future<PushOpen?> initialOpen() async {
    final m = await _fm.getInitialMessage();
    return m == null ? null : _toOpen(m);
  }

  static PushOpen _toOpen(RemoteMessage m) =>
      PushOpen(postingId: m.data['posting_id'] as String?);

  @override
  String? get platform =>
      defaultTargetPlatform == TargetPlatform.iOS ? 'ios' : 'android';
}
