import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/feed_repository.dart';
import '../../data/models/feed_models.dart';
import '../../data/providers.dart';
import '../../util/api_error.dart';

enum FeedStatus { loading, ready, error }

/// Feed ordering. `score` (default) puts the best matches first; `newest`
/// orders by the posting's publish date. The name maps 1:1 to the `sort` query
/// param the backend expects.
enum FeedSort {
  score('Best match'),
  newest('Newest');

  const FeedSort(this.label);
  final String label;
}

@immutable
class FeedState {
  const FeedState({
    this.status = FeedStatus.loading,
    this.items = const [],
    this.minScore = 1,
    this.sort = FeedSort.score,
    this.meta = const FeedMeta(),
    this.error,
  });

  final FeedStatus status;
  final List<FeedItem> items;

  /// The active minimum-score filter (`min_score` query param).
  final int minScore;

  /// The active ordering (`sort` query param).
  final FeedSort sort;

  /// Thin-feed context from the last load, powering the first-run nudges.
  final FeedMeta meta;
  final String? error;

  int get newCount => items.where((i) => i.isNew).length;
  bool get isEmpty => status == FeedStatus.ready && items.isEmpty;

  FeedState copyWith({
    FeedStatus? status,
    List<FeedItem>? items,
    int? minScore,
    FeedSort? sort,
    FeedMeta? meta,
    Object? error = _noChange,
  }) =>
      FeedState(
        status: status ?? this.status,
        items: items ?? this.items,
        minScore: minScore ?? this.minScore,
        sort: sort ?? this.sort,
        meta: meta ?? this.meta,
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
      final feed =
          await _repo.getFeed(minScore: state.minScore, sort: state.sort.name);
      state = state.copyWith(
          status: FeedStatus.ready, items: feed.items, meta: feed.meta,
          error: null);
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

  /// Change the ordering and reload.
  Future<void> setSort(FeedSort value) async {
    if (value == state.sort) return;
    state = state.copyWith(sort: value, status: FeedStatus.loading);
    await _load();
  }

  /// Optimistically flip the saved flag, rolling back if the call fails.
  Future<void> toggleSave(FeedItem item) async {
    final next = !item.saved;
    _patch(item.postingId, (i) => i.copyWith(saved: next));
    // Publish immediately so the Saved tab (and detail) reflect it without
    // waiting for the network.
    ref.read(savedOverridesProvider.notifier).set(item.postingId, next);
    try {
      await (next ? _repo.save(item.postingId) : _repo.unsave(item.postingId));
      ref.read(savedRevisionProvider.notifier).bump();
    } catch (e) {
      _patch(item.postingId, (i) => i.copyWith(saved: !next)); // rollback
      ref.read(savedOverridesProvider.notifier).set(item.postingId, !next);
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

  String _humanize(Object e) => apiErrorMessage(e);
}

final feedControllerProvider =
    NotifierProvider<FeedController, FeedState>(FeedController.new);
