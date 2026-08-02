import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/feed_repository.dart';
import '../../data/models/feed_models.dart';
import '../../data/providers.dart';
import '../../util/api_error.dart';

enum DetailStatus { loading, ready, error }

/// Async state of the "draft application" action.
enum DraftPhase { idle, running, done, failed }

@immutable
class JobDetailState {
  const JobDetailState({
    this.status = DetailStatus.loading,
    this.detail,
    this.error,
    this.draftPhase = DraftPhase.idle,
    this.draftError,
  });

  final DetailStatus status;
  final PostingDetail? detail;
  final String? error;
  final DraftPhase draftPhase;
  final String? draftError;

  JobDetailState copyWith({
    DetailStatus? status,
    PostingDetail? detail,
    Object? error = _noChange,
    DraftPhase? draftPhase,
    Object? draftError = _noChange,
  }) =>
      JobDetailState(
        status: status ?? this.status,
        detail: detail ?? this.detail,
        error: error == _noChange ? this.error : error as String?,
        draftPhase: draftPhase ?? this.draftPhase,
        draftError:
            draftError == _noChange ? this.draftError : draftError as String?,
      );

  static const _noChange = Object();
}

/// Loads one posting's full detail and owns its save/unsave and draft actions.
///
/// The screen calls [load] once with the posting id (the detail route is a
/// pushed full-screen page, so a single autoDispose controller per visit is
/// enough); it's recreated fresh each time the screen is opened.
class JobDetailController extends Notifier<JobDetailState> {
  FeedRepository get _repo => ref.read(feedRepositoryProvider);
  String? _postingId;

  @override
  JobDetailState build() => const JobDetailState();

  /// Load the posting's full detail. Safe to call once from initState.
  Future<void> load(String postingId) async {
    _postingId = postingId;
    state = const JobDetailState(status: DetailStatus.loading);
    try {
      final detail = await _repo.getPosting(postingId);
      state = state.copyWith(
          status: DetailStatus.ready, detail: detail, error: null);
    } catch (e) {
      state = state.copyWith(status: DetailStatus.error, error: _humanize(e));
    }
  }

  Future<void> refresh() async {
    if (_postingId != null) await load(_postingId!);
  }

  /// Optimistically flip saved, rolling back if the call fails.
  Future<void> toggleSave() async {
    final d = state.detail;
    if (d == null) return;
    final next = !d.saved;
    state = state.copyWith(detail: d.copyWith(saved: next));
    ref.read(savedOverridesProvider.notifier).set(d.postingId, next);
    try {
      await (next ? _repo.save(d.postingId) : _repo.unsave(d.postingId));
      ref.read(savedRevisionProvider.notifier).bump();
    } catch (e) {
      state = state.copyWith(
          detail: d.copyWith(saved: !next), error: _humanize(e));
      ref.read(savedOverridesProvider.notifier).set(d.postingId, !next);
    }
  }

  /// Kick off an application draft. The draft itself lands in the Applications
  /// tab (M5); here we just enqueue it and reflect the request.
  /// Start drafting an application. Returns the new draft's id (a 'pending' row
  /// the server created synchronously) so the caller can navigate straight to
  /// the application detail, which polls until it's ready. Null on failure.
  Future<String?> draft() async {
    final d = state.detail;
    if (d == null || state.draftPhase == DraftPhase.running) return null;
    state = state.copyWith(draftPhase: DraftPhase.running, draftError: null);
    try {
      final draftId = await _repo.createDraft(d.postingId);
      ref.read(draftedPostingIdsProvider.notifier).add(d.postingId);
      // A new (pending) draft row now exists — let the Applications tab show it.
      ref.read(draftsRevisionProvider.notifier).bump();
      state = state.copyWith(
        draftPhase: DraftPhase.done,
        detail: d.copyWith(drafted: true),
      );
      return draftId;
    } catch (e) {
      state = state.copyWith(
          draftPhase: DraftPhase.failed, draftError: _humanize(e));
      return null;
    }
  }

  String _humanize(Object e) => apiErrorMessage(e);
}

/// autoDispose so each detail visit starts clean and releases when popped.
final jobDetailControllerProvider =
    NotifierProvider.autoDispose<JobDetailController, JobDetailState>(
        JobDetailController.new);
