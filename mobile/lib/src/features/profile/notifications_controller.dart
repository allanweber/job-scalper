import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/account_models.dart';
import '../../data/providers.dart';
import '../../util/api_error.dart';

enum NotificationsStatus { loading, ready, error }

@immutable
class NotificationsState {
  const NotificationsState({
    this.status = NotificationsStatus.loading,
    this.prefs,
    this.error,
    this.saving = false,
  });

  final NotificationsStatus status;
  final NotificationPrefs? prefs;
  final String? error;
  final bool saving;

  NotificationsState copyWith({
    NotificationsStatus? status,
    NotificationPrefs? prefs,
    Object? error = _noChange,
    bool? saving,
  }) =>
      NotificationsState(
        status: status ?? this.status,
        prefs: prefs ?? this.prefs,
        error: error == _noChange ? this.error : error as String?,
        saving: saving ?? this.saving,
      );

  static const _noChange = Object();
}

/// Loads and edits the user's notification preferences (`/me/notifications`).
/// Changes are applied optimistically and persisted; on failure the previous
/// value is restored.
class NotificationsController extends Notifier<NotificationsState> {
  bool _disposed = false;

  @override
  NotificationsState build() {
    ref.onDispose(() => _disposed = true);
    Future.microtask(_load);
    return const NotificationsState();
  }

  Future<void> _load() async {
    try {
      final prefs = await ref.read(accountRepositoryProvider).getNotificationPrefs();
      if (_disposed) return;
      state = state.copyWith(
          status: NotificationsStatus.ready, prefs: prefs, error: null);
    } catch (e) {
      if (_disposed) return;
      state = state.copyWith(
          status: NotificationsStatus.error, error: apiErrorMessage(e));
    }
  }

  Future<void> refresh() => _load();

  void setMatchAlerts(bool value) {
    final current = state.prefs;
    if (current == null) return;
    _apply(current.copyWith(matchAlerts: value), current);
  }

  void setMinScore(int value) {
    final current = state.prefs;
    if (current == null) return;
    _apply(current.copyWith(minScore: value), current);
  }

  Future<void> _apply(NotificationPrefs next, NotificationPrefs previous) async {
    state = state.copyWith(prefs: next, saving: true);
    try {
      final saved =
          await ref.read(accountRepositoryProvider).saveNotificationPrefs(next);
      if (_disposed) return;
      state = state.copyWith(prefs: saved, saving: false);
    } catch (_) {
      if (_disposed) return;
      state = state.copyWith(prefs: previous, saving: false);
    }
  }
}

final notificationsControllerProvider =
    NotifierProvider.autoDispose<NotificationsController, NotificationsState>(
        NotificationsController.new);
