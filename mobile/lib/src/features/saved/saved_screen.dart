import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../theme/tokens.dart';
import '../feed/widgets/job_card.dart';
import 'saved_controller.dart';

/// The Saved tab: postings the user hearted, newest-scored first.
class SavedScreen extends ConsumerWidget {
  const SavedScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(savedControllerProvider);
    final ctrl = ref.read(savedControllerProvider.notifier);

    return Scaffold(
      appBar: AppBar(title: const Text('Saved'), centerTitle: false),
      body: switch (state.status) {
        SavedStatus.loading =>
          const Center(child: CircularProgressIndicator()),
        SavedStatus.error => _ErrorView(
            message: state.error ?? 'Something went wrong.',
            onRetry: ctrl.refresh,
          ),
        SavedStatus.ready => RefreshIndicator(
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
                      final item = state.items[i];
                      return JobCard(
                        item: item,
                        onToggleSave: () => ctrl.unsave(item),
                        onTap: () => context.push(
                            '/saved/job/${item.postingId}',
                            extra: item),
                      );
                    },
                  ),
          ),
      },
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
