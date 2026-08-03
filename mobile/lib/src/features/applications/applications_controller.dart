import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/drafts_repository.dart';
import '../../data/models/draft_models.dart';
import '../../data/providers.dart';
import '../../util/api_error.dart';

enum ApplicationsStatus { loading, ready, error }

@immutable
class ApplicationsState {
  const ApplicationsState({
    this.status = ApplicationsStatus.loading,
    this.items = const [],
    this.error,
  });

  final ApplicationsStatus status;
  final List<DraftSummary> items;
  final String? error;

  bool get isEmpty => status == ApplicationsStatus.ready && items.isEmpty;

  ApplicationsState copyWith({
    ApplicationsStatus? status,
    List<DraftSummary>? items,
    Object? error = _noChange,
  }) =>
      ApplicationsState(
        status: status ?? this.status,
        items: items ?? this.items,
        error: error == _noChange ? this.error : error as String?,
      );

  static const _noChange = Object();
}

/// The Applications tab: the user's drafts (`GET /drafts`), newest first. A
/// draft row is created the instant it's requested (status 'pending') and fills
/// in when the worker finishes, so rows here can be pending, ready or failed.
class ApplicationsController extends Notifier<ApplicationsState> {
  static const _pollEvery = Duration(seconds: 2);

  DraftsRepository get _repo => ref.read(draftsRepositoryProvider);
  bool _disposed = false;
  Timer? _pollTimer;

  @override
  ApplicationsState build() {
    ref.onDispose(() {
      _disposed = true;
      _pollTimer?.cancel();
    });
    // Reload when a draft is created or transitions elsewhere.
    ref.listen(draftsRevisionProvider, (_, _) => _load());
    Future.microtask(_load);
    return const ApplicationsState();
  }

  Future<void> _load() async {
    try {
      final items = await _repo.listDrafts();
      if (_disposed) return;
      state = state.copyWith(
          status: ApplicationsStatus.ready, items: items, error: null);
      _schedulePollIfPending();
    } catch (e) {
      if (_disposed) return;
      state =
          state.copyWith(status: ApplicationsStatus.error, error: _humanize(e));
    }
  }

  /// While any row is still drafting, reload periodically so the list flips it
  /// to ready/failed on its own (even if the user stays on this tab). The timer
  /// is cancellable so it never outlives the controller.
  void _schedulePollIfPending() {
    _pollTimer?.cancel();
    if (_disposed || !state.items.any((d) => d.isPending)) return;
    _pollTimer = Timer(_pollEvery, () {
      if (!_disposed) _load();
    });
  }

  Future<void> refresh() => _load();

  String _humanize(Object e) => apiErrorMessage(e);
}

final applicationsControllerProvider =
    NotifierProvider<ApplicationsController, ApplicationsState>(
        ApplicationsController.new);
