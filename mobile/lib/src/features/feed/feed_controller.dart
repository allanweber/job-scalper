import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/feed_repository.dart';
import '../../data/models/feed_models.dart';
import '../../data/providers.dart';

enum FeedStatus { loading, ready, error }

@immutable
class FeedState {
  const FeedState({
    this.status = FeedStatus.loading,
    this.items = const [],
    this.minScore = 1,
    this.error,
  });

  final FeedStatus status;
  final List<FeedItem> items;

  /// The active minimum-score filter (`min_score` query param).
  final int minScore;
  final String? error;

  int get newCount => items.where((i) => i.isNew).length;
  bool get isEmpty => status == FeedStatus.ready && items.isEmpty;

  FeedState copyWith({
    FeedStatus? status,
    List<FeedItem>? items,
    int? minScore,
    Object? error = _noChange,
  }) =>
      FeedState(
        status: status ?? this.status,
        items: items ?? this.items,
        minScore: minScore ?? this.minScore,
        error: error == _noChange ? this.error : error as String?,
      );

  static const _noChange = Object();
}

/// Loads and maintains the ranked feed: initial load, pull-to-refresh, the
/// score filter, optimistic save/unsave, and fire-and-forget seen-tracking.
class FeedController extends Notifier<FeedState> {
  FeedRepository get _repo => ref.read(feedRepositoryProvider);

  /// Postings already reported as seen this session (dedupes the POST).
  final Set<String> _seen = {};

  @override
  FeedState build() {
    // Defer so `state` is initialised before the first load reads it.
    Future.microtask(_load);
    return const FeedState();
  }

  Future<void> _load() async {
    try {
      final feed = await _repo.getFeed(minScore: state.minScore);
      state = state.copyWith(
          status: FeedStatus.ready, items: feed.items, error: null);
    } catch (e) {
      state = state.copyWith(status: FeedStatus.error, error: _humanize(e));
    }
  }

  /// Pull-to-refresh: reload without flipping to the full-screen spinner.
  Future<void> refresh() => _load();

  /// Change the minimum-score threshold and reload.
  Future<void> setMinScore(int value) async {
    if (value == state.minScore) return;
    state = state.copyWith(minScore: value, status: FeedStatus.loading);
    await _load();
  }

  /// Optimistically flip the saved flag, rolling back if the call fails.
  Future<void> toggleSave(FeedItem item) async {
    final next = !item.saved;
    _patch(item.postingId, (i) => i.copyWith(saved: next));
    try {
      await (next ? _repo.save(item.postingId) : _repo.unsave(item.postingId));
    } catch (e) {
      _patch(item.postingId, (i) => i.copyWith(saved: !next)); // rollback
      state = state.copyWith(error: _humanize(e));
    }
  }

  /// Called as a card scrolls into view; records "seen" once per posting.
  void onSeen(String postingId) {
    if (!_seen.add(postingId)) return;
    unawaited(_repo.markSeen(postingId).catchError((_) {}));
  }

  void _patch(String postingId, FeedItem Function(FeedItem) f) {
    state = state.copyWith(items: [
      for (final i in state.items)
        if (i.postingId == postingId) f(i) else i,
    ]);
  }

  String _humanize(Object e) {
    final s = e.toString();
    return s.startsWith('Exception: ') ? s.substring(11) : s;
  }
}

final feedControllerProvider =
    NotifierProvider<FeedController, FeedState>(FeedController.new);
