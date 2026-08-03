import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/drafts_repository.dart';
import '../../data/models/draft_models.dart';
import '../../data/providers.dart';
import '../../util/api_error.dart';

enum InsightsStatus { loading, ready, error }

@immutable
class InsightsState {
  const InsightsState({
    this.status = InsightsStatus.loading,
    this.insights,
    this.error,
  });

  final InsightsStatus status;
  final ApplicationInsights? insights;
  final String? error;

  InsightsState copyWith({
    InsightsStatus? status,
    ApplicationInsights? insights,
    Object? error = _noChange,
  }) =>
      InsightsState(
        status: status ?? this.status,
        insights: insights ?? this.insights,
        error: error == _noChange ? this.error : error as String?,
      );

  static const _noChange = Object();
}

/// Loads the application funnel for the Insights screen and reloads it whenever
/// a draft is created or its stage changes (via [draftsRevisionProvider]), so
/// the flow chart stays in step with the Applications list.
class ApplicationInsightsController extends Notifier<InsightsState> {
  DraftsRepository get _repo => ref.read(draftsRepositoryProvider);
  bool _disposed = false;

  @override
  InsightsState build() {
    ref.onDispose(() => _disposed = true);
    ref.listen(draftsRevisionProvider, (_, _) => _load());
    Future.microtask(_load);
    return const InsightsState();
  }

  Future<void> _load() async {
    try {
      final insights = await _repo.getInsights();
      if (_disposed) return;
      state = state.copyWith(
          status: InsightsStatus.ready, insights: insights, error: null);
    } catch (e) {
      if (_disposed) return;
      state = state.copyWith(
          status: InsightsStatus.error, error: apiErrorMessage(e));
    }
  }

  Future<void> refresh() => _load();
}

final applicationInsightsControllerProvider =
    NotifierProvider.autoDispose<ApplicationInsightsController, InsightsState>(
        ApplicationInsightsController.new);
