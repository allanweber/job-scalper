import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/account_models.dart';
import '../../data/providers.dart';

@immutable
class BoardsState {
  const BoardsState({
    this.loading = true,
    this.saving = false,
    this.info,
    this.selected = const [],
    this.error,
  });

  final bool loading;
  final bool saving;
  final SourcesInfo? info;
  final List<String> selected;
  final String? error;

  int get maxAllowed => info?.maxAllowed ?? 3;
  List<String> get available => info?.available ?? const [];
  bool get atLimit => selected.length >= maxAllowed;

  bool get dirty =>
      info != null &&
      (selected.length != info!.selected.length ||
          !selected.every(info!.selected.contains));

  BoardsState copyWith({
    bool? loading,
    bool? saving,
    SourcesInfo? info,
    List<String>? selected,
    Object? error = _sentinel,
  }) =>
      BoardsState(
        loading: loading ?? this.loading,
        saving: saving ?? this.saving,
        info: info ?? this.info,
        selected: selected ?? this.selected,
        error: error == _sentinel ? this.error : error as String?,
      );

  static const _sentinel = Object();
}

/// Backs the Job boards editor: which boards to scan, capped at [maxAllowed].
class BoardsController extends Notifier<BoardsState> {
  @override
  BoardsState build() {
    _load();
    return const BoardsState();
  }

  Future<void> _load() async {
    try {
      final info = await ref.read(accountRepositoryProvider).getSources();
      state = state.copyWith(
          loading: false, info: info, selected: List.of(info.selected));
    } catch (e) {
      state = state.copyWith(loading: false, error: '$e');
    }
  }

  /// Toggle a board; returns false if the toggle was rejected (over the cap).
  bool toggle(String slug) {
    if (state.selected.contains(slug)) {
      state = state.copyWith(
          selected: state.selected.where((s) => s != slug).toList(),
          error: null);
      return true;
    }
    if (state.atLimit) return false;
    state = state.copyWith(selected: [...state.selected, slug], error: null);
    return true;
  }

  Future<bool> save() async {
    state = state.copyWith(saving: true, error: null);
    try {
      final info =
          await ref.read(accountRepositoryProvider).saveSources(state.selected);
      state = state.copyWith(
          saving: false, info: info, selected: List.of(info.selected));
      return true;
    } catch (e) {
      state = state.copyWith(saving: false, error: '$e');
      return false;
    }
  }
}

final boardsControllerProvider =
    NotifierProvider.autoDispose<BoardsController, BoardsState>(
        BoardsController.new);
