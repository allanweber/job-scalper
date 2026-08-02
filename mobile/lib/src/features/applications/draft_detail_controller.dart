import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/drafts_repository.dart';
import '../../data/models/draft_models.dart';
import '../../data/pdf_cache_repository.dart';
import '../../data/providers.dart';

enum DraftDetailStatus { loading, ready, error }

/// Which document of a draft is on screen / being edited.
enum DraftDoc { resume, coverLetter }

@immutable
class DraftDetailState {
  const DraftDetailState({
    this.status = DraftDetailStatus.loading,
    this.draft,
    this.error,
    this.saving = false,
    this.saveError,
  });

  final DraftDetailStatus status;
  final Draft? draft;
  final String? error;
  final bool saving;
  final String? saveError;

  DraftDetailState copyWith({
    DraftDetailStatus? status,
    Draft? draft,
    Object? error = _noChange,
    bool? saving,
    Object? saveError = _noChange,
  }) =>
      DraftDetailState(
        status: status ?? this.status,
        draft: draft ?? this.draft,
        error: error == _noChange ? this.error : error as String?,
        saving: saving ?? this.saving,
        saveError:
            saveError == _noChange ? this.saveError : saveError as String?,
      );

  static const _noChange = Object();
}

/// Loads one draft and owns its per-document edits. The screen calls [load]
/// once from initState (the detail route is a pushed page), so a single
/// autoDispose controller per visit is enough.
class DraftDetailController extends Notifier<DraftDetailState> {
  DraftsRepository get _repo => ref.read(draftsRepositoryProvider);
  PdfCacheRepository get _pdfCache => ref.read(pdfCacheRepositoryProvider);
  String? _id;

  @override
  DraftDetailState build() => const DraftDetailState();

  Future<void> load(String id) async {
    _id = id;
    state = const DraftDetailState(status: DraftDetailStatus.loading);
    try {
      final draft = await _repo.getDraft(id);
      state = state.copyWith(
          status: DraftDetailStatus.ready, draft: draft, error: null);
    } catch (e) {
      state =
          state.copyWith(status: DraftDetailStatus.error, error: _humanize(e));
    }
  }

  Future<void> refresh() async {
    if (_id != null) await load(_id!);
  }

  /// Persist an edit to one document. Returns true on success (so the editor
  /// can pop); on failure the state carries [saveError] and stays open.
  Future<bool> saveDoc(DraftDoc doc, String markdown) async {
    final d = state.draft;
    if (d == null) return false;
    state = state.copyWith(saving: true, saveError: null);
    try {
      final updated = await _repo.updateDraft(
        d.id,
        resumeMd: doc == DraftDoc.resume ? markdown : null,
        coverLetterMd: doc == DraftDoc.coverLetter ? markdown : null,
      );
      // Edited markdown invalidates any cached PDF for this draft.
      await _pdfCache.invalidate(d.id);
      state = state.copyWith(draft: updated, saving: false);
      return true;
    } catch (e) {
      state = state.copyWith(saving: false, saveError: _humanize(e));
      return false;
    }
  }

  String _humanize(Object e) {
    final s = e.toString();
    return s.startsWith('Exception: ') ? s.substring(11) : s;
  }
}

final draftDetailControllerProvider =
    NotifierProvider.autoDispose<DraftDetailController, DraftDetailState>(
        DraftDetailController.new);
