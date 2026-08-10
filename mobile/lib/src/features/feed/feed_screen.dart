import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../data/models/feed_models.dart';
import '../../data/providers.dart';
import '../../theme/tokens.dart';
import '../../util/api_error.dart';
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
        actions: [
          PopupMenuButton<FeedSort>(
            icon: const Icon(Icons.sort_rounded),
            tooltip: 'Sort',
            initialValue: state.sort,
            onSelected: ctrl.setSort,
            itemBuilder: (context) => [
              for (final s in FeedSort.values)
                CheckedPopupMenuItem(
                  value: s,
                  checked: s == state.sort,
                  child: Text(s.label),
                ),
            ],
          ),
          IconButton(
            icon: const Icon(Icons.add_link_rounded),
            tooltip: 'Add job from URL',
            onPressed: () => _showImportDialog(context, ref),
          ),
        ],
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
                ? _EmptyView(state: state, ctrl: ctrl)
                : _FeedList(ref: ref),
          ),
      },
    );
  }
}

/// Opens the "add job from URL" dialog; on a successful import, navigates to the
/// imported posting's detail so the user can draft an application against it.
Future<void> _showImportDialog(BuildContext context, WidgetRef ref) async {
  final repo = ref.read(feedRepositoryProvider);
  final detail = await showDialog<PostingDetail>(
    context: context,
    builder: (_) => _ImportUrlDialog(onImport: repo.importUrl),
  );
  if (detail != null && context.mounted) {
    context.push('/feed/job/${detail.postingId}');
  }
}

/// Paste-a-link dialog. Fetches/scores the URL via the repository, showing a
/// busy state while it runs and the backend's message inline on failure; pops
/// the imported [PostingDetail] on success.
class _ImportUrlDialog extends StatefulWidget {
  const _ImportUrlDialog({required this.onImport});
  final Future<PostingDetail> Function(String url) onImport;

  @override
  State<_ImportUrlDialog> createState() => _ImportUrlDialogState();
}

class _ImportUrlDialogState extends State<_ImportUrlDialog> {
  final _controller = TextEditingController();
  bool _busy = false;
  String? _error;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final url = _controller.text.trim();
    if (url.isEmpty) {
      setState(() => _error = 'Paste a job posting link.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final detail = await widget.onImport(url);
      if (mounted) Navigator.of(context).pop(detail);
    } catch (e) {
      if (mounted) {
        setState(() {
          _busy = false;
          _error = apiErrorMessage(e);
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return AlertDialog(
      title: const Text('Add job from URL'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            "Paste a link to a job posting. We'll fetch it, score it against "
            'your profile, and let you draft an application.',
            style: TextStyle(fontSize: 13, color: scheme.onSurfaceVariant),
          ),
          const SizedBox(height: 14),
          TextField(
            controller: _controller,
            autofocus: true,
            enabled: !_busy,
            keyboardType: TextInputType.url,
            textInputAction: TextInputAction.go,
            onSubmitted: (_) => _busy ? null : _submit(),
            decoration: const InputDecoration(
              hintText: 'https://…',
              prefixIcon: Icon(Icons.link_rounded),
            ),
          ),
          if (_error != null) ...[
            const SizedBox(height: 10),
            Text(_error!,
                style: TextStyle(fontSize: 12.5, color: scheme.error)),
          ],
        ],
      ),
      actions: [
        TextButton(
          onPressed: _busy ? null : () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _busy ? null : _submit,
          child: _busy
              ? const SizedBox(
                  height: 18,
                  width: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Text('Add'),
        ),
      ],
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
    final localDrafted = ref.watch(draftedPostingIdsProvider);
    final appliedOverrides = ref.watch(appliedOverridesProvider);
    final savedOverrides = ref.watch(savedOverridesProvider);
    final items = state.items;
    final hasBanner = state.newCount > 0;
    // A gentle "add boards" nudge under a short list, so a thin first feed
    // points at the lever that widens it.
    final hasFooter = state.meta.canAddBoards && items.length <= 4;

    return ListView.separated(
      padding: const EdgeInsets.fromLTRB(AppTokens.screenPadding, 12,
          AppTokens.screenPadding, 24),
      itemCount: items.length + (hasBanner ? 1 : 0) + (hasFooter ? 1 : 0),
      separatorBuilder: (_, _) => const SizedBox(height: AppTokens.listGap),
      itemBuilder: (context, index) {
        if (hasBanner && index == 0) {
          return _NewMatchesBanner(count: state.newCount);
        }
        final base = index - (hasBanner ? 1 : 0);
        if (hasFooter && base == items.length) {
          return const _ThinFeedFooter();
        }
        final raw = items[base];
        var item = raw;
        final savedOverride = savedOverrides[raw.postingId];
        if (savedOverride != null) {
          item = item.copyWith(saved: savedOverride);
        }
        if (localDrafted.contains(raw.postingId)) {
          item = item.copyWith(drafted: true);
        }
        final override = appliedOverrides[raw.postingId];
        if (override != null) {
          // Applied implies a draft exists, so keep the drafted flag set too.
          item = item.copyWith(
              applied: override, drafted: override || item.drafted);
        }
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

/// The Feed's empty state. The heading is constant ("No matches yet"), but the
/// body and call-to-action adapt to *why* it's empty — no profile, a score
/// filter hiding real matches, or room to add boards — so a new user's first
/// dead-end points straight at the one action that fixes it.
class _EmptyView extends StatelessWidget {
  const _EmptyView({required this.state, required this.ctrl});
  final FeedState state;
  final FeedController ctrl;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final nudge = _nudge(context);
    // Scrollable so pull-to-refresh still works with no items.
    return ListView(
      children: [
        SizedBox(height: MediaQuery.of(context).size.height * 0.18),
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
            nudge.body,
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: 13.5, color: scheme.onSurfaceVariant),
          ),
        ),
        if (nudge.action != null) ...[
          const SizedBox(height: 20),
          Center(child: nudge.action!),
        ],
      ],
    );
  }

  ({String body, Widget? action}) _nudge(BuildContext context) {
    final meta = state.meta;
    if (!meta.hasProfile) {
      return (
        body: 'Add your profile so we can match jobs to you.',
        action: FilledButton.tonal(
          onPressed: () => context.push('/profile/edit'),
          child: const Text('Complete your profile'),
        ),
      );
    }
    if (meta.poolSize > 0 && state.minScore > 1) {
      final n = meta.poolSize;
      return (
        body: '$n ${n == 1 ? 'job' : 'jobs'} on your boards scored below '
            '${state.minScore}. Show everything to see them.',
        action: FilledButton.tonal(
          onPressed: () => ctrl.setMinScore(1),
          child: const Text('Show all matches'),
        ),
      );
    }
    if (meta.canAddBoards) {
      return (
        body: 'We check your boards regularly. Add more job boards to widen '
            'your search.',
        action: FilledButton.tonal(
          onPressed: () => context.push('/profile/boards'),
          child: const Text('Add job boards'),
        ),
      );
    }
    return (
      body: 'We check your boards regularly — new roles will show up here. '
          'Pull down to refresh.',
      action: null,
    );
  }
}

/// A quiet footer under a short feed, nudging the user to widen their search by
/// adding boards.
class _ThinFeedFooter extends StatelessWidget {
  const _ThinFeedFooter();

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 10, 8, 10),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(AppTokens.radiusCard),
      ),
      child: Row(
        children: [
          Icon(Icons.tune_rounded, size: 18, color: scheme.onSurfaceVariant),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              'Seeing only a few? Add more job boards to widen your search.',
              style: TextStyle(fontSize: 13, color: scheme.onSurfaceVariant),
            ),
          ),
          const SizedBox(width: 4),
          TextButton(
            onPressed: () => context.push('/profile/boards'),
            child: const Text('Add boards'),
          ),
        ],
      ),
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
