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

/// The Applications tab: the user's generated drafts (`GET /drafts`), newest
/// first. A draft only exists once its background job succeeded, so every row
/// here is a finished, viewable application.
class ApplicationsController extends Notifier<ApplicationsState> {
  DraftsRepository get _repo => ref.read(draftsRepositoryProvider);

  @override
  ApplicationsState build() {
    Future.microtask(_load);
    return const ApplicationsState();
  }

  Future<void> _load() async {
    try {
      final items = await _repo.listDrafts();
      state = state.copyWith(
          status: ApplicationsStatus.ready, items: items, error: null);
    } catch (e) {
      state =
          state.copyWith(status: ApplicationsStatus.error, error: _humanize(e));
    }
  }

  Future<void> refresh() => _load();

  String _humanize(Object e) => apiErrorMessage(e);
}

final applicationsControllerProvider =
    NotifierProvider<ApplicationsController, ApplicationsState>(
        ApplicationsController.new);
