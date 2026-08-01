import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../theme/tokens.dart';
import 'feed_controller.dart';
import 'widgets/job_card.dart';

/// The Feed tab: the ranked list of postings the whole app exists to surface.
class FeedScreen extends ConsumerWidget {
  const FeedScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(feedControllerProvider);
    final ctrl = ref.read(feedControllerProvider.notifier);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Feed'),
        centerTitle: false,
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(52),
          child: _FilterBar(
            minScore: state.minScore,
            onChanged: ctrl.setMinScore,
          ),
        ),
      ),
      body: switch (state.status) {
        FeedStatus.loading => const Center(child: CircularProgressIndicator()),
        FeedStatus.error => _ErrorView(
            message: state.error ?? 'Something went wrong.',
            onRetry: ctrl.refresh,
          ),
        FeedStatus.ready => RefreshIndicator(
            onRefresh: ctrl.refresh,
            child: state.isEmpty
                ? const _EmptyView()
                : _FeedList(ref: ref),
          ),
      },
    );
  }
}

class _FeedList extends StatelessWidget {
  const _FeedList({required this.ref});
  final WidgetRef ref;

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(feedControllerProvider);
    final ctrl = ref.read(feedControllerProvider.notifier);
    final items = state.items;
    final hasBanner = state.newCount > 0;

    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(AppTokens.screenPadding, 12,
          AppTokens.screenPadding, 24),
      itemCount: items.length + (hasBanner ? 1 : 0),
      separatorBuilder: (_, _) => const SizedBox(height: AppTokens.listGap),
      itemBuilder: (context, index) {
        if (hasBanner && index == 0) {
          return _NewMatchesBanner(count: state.newCount);
        }
        final item = items[index - (hasBanner ? 1 : 0)];
        // Building lazily ~ scrolled into view: record it as seen (deduped).
        ctrl.onSeen(item.postingId);
        return JobCard(
          item: item,
          onToggleSave: () => ctrl.toggleSave(item),
          onTap: () =>
              context.push('/feed/job/${item.postingId}', extra: item),
        );
      },
    );
  }
}

class _FilterBar extends StatelessWidget {
  const _FilterBar({required this.minScore, required this.onChanged});
  final int minScore;
  final ValueChanged<int> onChanged;

  static const _options = [
    (label: 'All', value: 1),
    (label: '55+', value: 55),
    (label: '70+', value: 70),
    (label: '85+', value: 85),
  ];

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 52,
      child: ListView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(
            horizontal: AppTokens.screenPadding, vertical: 8),
        children: [
          for (final o in _options) ...[
            ChoiceChip(
              label: Text(o.label),
              selected: minScore == o.value,
              onSelected: (_) => onChanged(o.value),
            ),
            const SizedBox(width: 8),
          ],
        ],
      ),
    );
  }
}

class _NewMatchesBanner extends StatelessWidget {
  const _NewMatchesBanner({required this.count});
  final int count;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: scheme.primaryContainer,
        borderRadius: BorderRadius.circular(AppTokens.radiusCard),
      ),
      child: Row(
        children: [
          Icon(Icons.auto_awesome_rounded,
              size: 18, color: scheme.onPrimaryContainer),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              count == 1 ? '1 new match since you last looked'
                  : '$count new matches since you last looked',
              style: TextStyle(
                  fontSize: 13.5,
                  fontWeight: FontWeight.w600,
                  color: scheme.onPrimaryContainer),
            ),
          ),
        ],
      ),
    );
  }
}

class _EmptyView extends StatelessWidget {
  const _EmptyView();

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    // Scrollable so pull-to-refresh still works with no items.
    return ListView(
      children: [
        SizedBox(height: MediaQuery.of(context).size.height * 0.22),
        Icon(Icons.travel_explore_rounded,
            size: 56, color: scheme.onSurfaceVariant),
        const SizedBox(height: 16),
        Center(
          child: Text('No matches yet',
              style: TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.w700,
                  color: scheme.onSurface)),
        ),
        const SizedBox(height: 8),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 40),
          child: Text(
            'We check your boards regularly. Lower the score filter, or pull to '
            'refresh.',
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
            Text('Couldn’t load your feed',
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
