import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/feed_repository.dart';
import '../../data/models/feed_models.dart';
import '../../data/providers.dart';
import '../../util/api_error.dart';

enum SavedStatus { loading, ready, error }

@immutable
class SavedState {
  const SavedState({
    this.status = SavedStatus.loading,
    this.items = const [],
    this.error,
  });

  final SavedStatus status;
  final List<FeedItem> items;
  final String? error;

  bool get isEmpty => status == SavedStatus.ready && items.isEmpty;

  SavedState copyWith({
    SavedStatus? status,
    List<FeedItem>? items,
    Object? error = _noChange,
  }) =>
      SavedState(
        status: status ?? this.status,
        items: items ?? this.items,
        error: error == _noChange ? this.error : error as String?,
      );

  static const _noChange = Object();
}

/// The Saved tab. There's no dedicated saved endpoint, so this pulls the full
/// scored feed (min_score 0) and keeps the saved postings — showing every saved
/// posting still in the pool regardless of its score.
class SavedController extends Notifier<SavedState> {
  FeedRepository get _repo => ref.read(feedRepositoryProvider);

  @override
  SavedState build() {
    // Reload in the background whenever a posting is saved/unsaved elsewhere
    // (feed or job detail), so this tab stays current without a manual refresh.
    // _load swaps items in place without a loading state, so there's no flash.
    ref.listen(savedRevisionProvider, (_, _) => _load());
    Future.microtask(_load);
    return const SavedState();
  }

  Future<void> _load() async {
    try {
      final feed = await _repo.getFeed(minScore: 0, limit: 500);
      final saved = feed.items.where((i) => i.saved).toList();
      state =
          state.copyWith(status: SavedStatus.ready, items: saved, error: null);
    } catch (e) {
      state = state.copyWith(status: SavedStatus.error, error: _humanize(e));
    }
  }

  Future<void> refresh() => _load();

  /// Unsave optimistically removes the card; a failure restores it.
  Future<void> unsave(FeedItem item) async {
    final before = state.items;
    state = state.copyWith(
        items: [for (final i in before) if (i.postingId != item.postingId) i]);
    try {
      await _repo.unsave(item.postingId);
    } catch (e) {
      state = state.copyWith(items: before, error: _humanize(e));
    }
  }

  String _humanize(Object e) => apiErrorMessage(e);
}

final savedControllerProvider =
    NotifierProvider<SavedController, SavedState>(SavedController.new);
