import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../data/models/draft_models.dart';
import '../../data/providers.dart';
import '../../theme/tokens.dart';
import '../../util/format.dart';
import 'application_status.dart';
import 'applications_controller.dart';

/// The Applications tab: tailored resume + cover-letter drafts the user has
/// generated, newest first. Tap one to read and edit it.
class ApplicationsScreen extends ConsumerWidget {
  const ApplicationsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(applicationsControllerProvider);
    final ctrl = ref.read(applicationsControllerProvider.notifier);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Applications'),
        centerTitle: false,
        actions: [
          IconButton(
            tooltip: 'Insights',
            onPressed: () => context.push('/applications/insights'),
            icon: const Icon(Icons.insights_outlined),
          ),
        ],
      ),
      body: switch (state.status) {
        ApplicationsStatus.loading =>
          const Center(child: CircularProgressIndicator()),
        ApplicationsStatus.error => _ErrorView(
            message: state.error ?? 'Something went wrong.',
            onRetry: ctrl.refresh,
          ),
        ApplicationsStatus.ready => RefreshIndicator(
            onRefresh: ctrl.refresh,
            child: state.isEmpty
                ? const _EmptyView()
                : ListView.separated(
                    padding: const EdgeInsets.fromLTRB(AppTokens.screenPadding,
                        12, AppTokens.screenPadding, 24),
                    itemCount: state.items.length,
                    separatorBuilder: (_, _) =>
                        const SizedBox(height: AppTokens.listGap),
                    itemBuilder: (context, i) {
                      final d = state.items[i];
                      // A session-local stage override (set the instant the user
                      // changes it on the detail) wins over the loaded value;
                      // fall back to 'applied' for a draft flagged applied
                      // without an explicit stage (pre-pipeline data).
                      final overrides =
                          ref.watch(applicationStatusOverridesProvider);
                      final base =
                          d.applicationStatus ?? (d.applied ? 'applied' : null);
                      final stage =
                          d.postingId != null && overrides.containsKey(d.postingId)
                              ? overrides[d.postingId]
                              : base;
                      return Dismissible(
                        key: ValueKey(d.id),
                        direction: DismissDirection.endToStart,
                        confirmDismiss: (_) => _confirmDelete(context, d),
                        onDismissed: (_) => ctrl.delete(d.id),
                        background: const _DeleteBackground(),
                        child: _ApplicationCard(
                          draft: d,
                          stage: stage,
                          onTap: () => context.push(
                              '/applications/draft/${d.id}',
                              extra: d),
                        ),
                      );
                    },
                  ),
          ),
      },
    );
  }
}

Future<bool> _confirmDelete(BuildContext context, DraftSummary d) async {
  final ok = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(
          d.isFailed ? 'Remove failed application?' : 'Delete this application?'),
      content: const Text(
          'This removes the draft from your applications and can’t be undone.'),
      actions: [
        TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Cancel')),
        FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: const Text('Delete')),
      ],
    ),
  );
  return ok ?? false;
}

/// The red "swipe to delete" background revealed behind an Applications row.
class _DeleteBackground extends StatelessWidget {
  const _DeleteBackground();

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      alignment: Alignment.centerRight,
      padding: const EdgeInsets.only(right: 22),
      decoration: BoxDecoration(
        color: scheme.errorContainer,
        borderRadius: BorderRadius.circular(AppTokens.radiusCard),
      ),
      child: Icon(Icons.delete_outline_rounded, color: scheme.onErrorContainer),
    );
  }
}

class _ApplicationCard extends StatelessWidget {
  const _ApplicationCard({
    required this.draft,
    required this.stage,
    required this.onTap,
  });
  final DraftSummary draft;

  /// The effective application pipeline stage (override-aware), or null when
  /// not applied.
  final String? stage;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final when = relativeTime(draft.createdAt);
    final subtitleBits = <String>[
      if (draft.company != null && draft.company!.isNotEmpty) draft.company!,
    ];
    if (when != null) subtitleBits.add(when);

    return Material(
      color: scheme.surface,
      borderRadius: BorderRadius.circular(AppTokens.radiusCard),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppTokens.radiusCard),
        child: Padding(
          padding: const EdgeInsets.all(AppTokens.cardPadding),
          child: Row(
            children: [
              _Leading(status: draft.status, scheme: scheme),
              const SizedBox(width: 14),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      draft.displayTitle,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                          fontSize: 15.5,
                          fontWeight: FontWeight.w700,
                          color: scheme.onSurface),
                    ),
                    if (subtitleBits.isNotEmpty) ...[
                      const SizedBox(height: 3),
                      Text(
                        subtitleBits.join(' · '),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                            fontSize: 13, color: scheme.onSurfaceVariant),
                      ),
                    ],
                    if (draft.isPending || draft.isFailed) ...[
                      const SizedBox(height: 6),
                      _StatusPill(status: draft.status, scheme: scheme),
                    ],
                  ],
                ),
              ),
              if (draft.isReady && stage != null) ...[
                const SizedBox(width: 8),
                _StagePill(stage: stage!),
              ],
              const SizedBox(width: 8),
              Icon(Icons.chevron_right_rounded, color: scheme.onSurfaceVariant),
            ],
          ),
        ),
      ),
    );
  }
}

/// The card's leading badge: a spinner while drafting, an error mark on
/// failure, otherwise the document icon.
class _Leading extends StatelessWidget {
  const _Leading({required this.status, required this.scheme});
  final String status;
  final ColorScheme scheme;

  @override
  Widget build(BuildContext context) {
    final (bg, child) = switch (status) {
      'pending' => (
          scheme.surfaceContainerHighest,
          const SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(strokeWidth: 2.4)),
        ),
      'failed' => (
          scheme.errorContainer,
          Icon(Icons.error_outline_rounded,
              color: scheme.onErrorContainer, size: 22),
        ),
      _ => (
          scheme.primaryContainer,
          Icon(Icons.description_rounded,
              color: scheme.onPrimaryContainer, size: 22),
        ),
    };
    return Container(
      width: 42,
      height: 42,
      alignment: Alignment.center,
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(12),
      ),
      child: child,
    );
  }
}

/// A small status chip for a pending/failed draft.
class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.status, required this.scheme});
  final String status;
  final ColorScheme scheme;

  @override
  Widget build(BuildContext context) {
    final failed = status == 'failed';
    final label = failed ? 'Failed' : 'Drafting…';
    final fg = failed ? scheme.error : scheme.onSurfaceVariant;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: failed
            ? scheme.errorContainer.withValues(alpha: 0.5)
            : scheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(label,
          style: TextStyle(
              fontSize: 11, fontWeight: FontWeight.w700, color: fg)),
    );
  }
}

/// The card's trailing pipeline-stage badge (Applied / Interviewing / Offer /
/// Rejected), each in its own color so the list scans like a pipeline board.
class _StagePill extends StatelessWidget {
  const _StagePill({required this.stage});
  final String stage;

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final colors = applicationStageColors(stage, dark);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(
        color: colors.bg,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(applicationStageLabel(stage),
          style: TextStyle(
              fontSize: 11, fontWeight: FontWeight.w700, color: colors.fg)),
    );
  }
}

class _EmptyView extends StatelessWidget {
  const _EmptyView();

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return ListView(
      children: [
        SizedBox(height: MediaQuery.of(context).size.height * 0.2),
        Icon(Icons.description_outlined,
            size: 56, color: scheme.onSurfaceVariant),
        const SizedBox(height: 16),
        Center(
          child: Text('No applications yet',
              style: TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.w700,
                  color: scheme.onSurface)),
        ),
        const SizedBox(height: 8),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 40),
          child: Text(
            'Open a job and tap “Draft application” to generate a tailored '
            'resume and cover letter. They’ll show up here.',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 13.5, color: scheme.onSurfaceVariant),
          ),
        ),
        const SizedBox(height: 20),
        Center(
          child: FilledButton.tonal(
            onPressed: () => context.go('/feed'),
            child: const Text('Browse the feed'),
          ),
        ),
      ],
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.cloud_off_rounded,
                size: 48, color: scheme.onSurfaceVariant),
            const SizedBox(height: 16),
            Text('Couldn’t load your applications',
                style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: scheme.onSurface)),
            const SizedBox(height: 8),
            Text(message,
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 13, color: scheme.onSurfaceVariant)),
            const SizedBox(height: 20),
            FilledButton.tonal(onPressed: onRetry, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }
}
