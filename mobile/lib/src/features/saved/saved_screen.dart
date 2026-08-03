import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../data/models/feed_models.dart';
import '../../data/providers.dart';
import '../../theme/tokens.dart';
import '../feed/feed_controller.dart';
import '../feed/widgets/job_card.dart';
import 'saved_controller.dart';

/// The Saved tab: postings the user hearted, highest-scored first.
///
/// The display list merges the controller's own load (all saved postings,
/// regardless of score) with any items the feed already has, then applies the
/// session-local saved override. That override is written the instant the heart
/// is tapped anywhere, so a save/unsave shows here immediately — a newly saved
/// feed job appears, an unsaved one drops off — without waiting for a reload.
class SavedScreen extends ConsumerWidget {
  const SavedScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(savedControllerProvider);
    final ctrl = ref.read(savedControllerProvider.notifier);
    final feedItems = ref.watch(feedControllerProvider).items;
    final savedOverrides = ref.watch(savedOverridesProvider);
    final appliedOverrides = ref.watch(appliedOverridesProvider);

    // Merge by posting id (the controller's own saved item is authoritative for
    // the object), apply the saved override, keep only what's still saved.
    final byId = <String, FeedItem>{};
    for (final i in feedItems) {
      byId[i.postingId] = i;
    }
    for (final i in state.items) {
      byId[i.postingId] = i;
    }
    final items = byId.values
        .map((i) {
          final s = savedOverrides[i.postingId];
          return s == null ? i : i.copyWith(saved: s);
        })
        .where((i) => i.saved)
        .toList()
      ..sort((a, b) => b.score.compareTo(a.score));

    Widget body;
    if (items.isEmpty && state.status == SavedStatus.loading) {
      body = const Center(child: CircularProgressIndicator());
    } else if (items.isEmpty && state.status == SavedStatus.error) {
      body = _ErrorView(
        message: state.error ?? 'Something went wrong.',
        onRetry: ctrl.refresh,
      );
    } else {
      body = RefreshIndicator(
        onRefresh: ctrl.refresh,
        child: items.isEmpty
            ? const _EmptyView()
            : ListView.separated(
                padding: const EdgeInsets.fromLTRB(
                    AppTokens.screenPadding, 12, AppTokens.screenPadding, 24),
                itemCount: items.length,
                separatorBuilder: (_, _) =>
                    const SizedBox(height: AppTokens.listGap),
                itemBuilder: (context, i) {
                  final raw = items[i];
                  final applied = appliedOverrides[raw.postingId];
                  final item = applied == null
                      ? raw
                      : raw.copyWith(
                          applied: applied, drafted: applied || raw.drafted);
                  return JobCard(
                    item: item,
                    onToggleSave: () => ctrl.unsave(item),
                    onTap: () => context.push('/saved/job/${item.postingId}',
                        extra: item),
                  );
                },
              ),
      );
    }

    return Scaffold(
      appBar: AppBar(title: const Text('Saved'), centerTitle: false),
      body: body,
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
        SizedBox(height: MediaQuery.of(context).size.height * 0.22),
        Icon(Icons.favorite_outline, size: 56, color: scheme.onSurfaceVariant),
        const SizedBox(height: 16),
        Center(
          child: Text('Nothing saved yet',
              style: TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.w700,
                  color: scheme.onSurface)),
        ),
        const SizedBox(height: 8),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 40),
          child: Text(
            'Tap the heart on any job in your feed to keep it here.',
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 13.5, color: scheme.onSurfaceVariant),
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
            Text('Couldn’t load saved jobs',
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
