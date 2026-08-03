import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../data/models/draft_models.dart';
import '../../theme/tokens.dart';
import 'application_flow_chart.dart';
import 'application_insights_controller.dart';

/// The Insights screen: a Sankey funnel of the user's applications plus a few
/// headline rates. Reached from the chart icon on the Applications tab.
class ApplicationInsightsScreen extends ConsumerWidget {
  const ApplicationInsightsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(applicationInsightsControllerProvider);
    final ctrl = ref.read(applicationInsightsControllerProvider.notifier);

    return Scaffold(
      appBar: AppBar(title: const Text('Insights'), centerTitle: false),
      body: switch (state.status) {
        InsightsStatus.loading =>
          const Center(child: CircularProgressIndicator()),
        InsightsStatus.error => _ErrorView(
            message: state.error ?? 'Something went wrong.',
            onRetry: ctrl.refresh,
          ),
        InsightsStatus.ready => RefreshIndicator(
            onRefresh: ctrl.refresh,
            child: (state.insights?.total ?? 0) == 0
                ? const _EmptyView()
                : _Ready(insights: state.insights!),
          ),
      },
    );
  }
}

class _Ready extends StatelessWidget {
  const _Ready({required this.insights});
  final ApplicationInsights insights;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    int v(String s) => insights.stage(s);
    final total = insights.total;
    final interviews = v('interviewing') + v('offer');
    final offers = v('offer');
    final ghostPct = total == 0 ? 0 : (v('ghosted') * 100 / total).round();

    return ListView(
      padding: const EdgeInsets.fromLTRB(AppTokens.screenPadding, 12,
          AppTokens.screenPadding, 28),
      children: [
        Text('$total ${total == 1 ? 'application' : 'applications'}',
            style: TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.w800,
                color: scheme.onSurface)),
        const SizedBox(height: 2),
        Text('Where your applications stand',
            style: TextStyle(fontSize: 13, color: scheme.onSurfaceVariant)),
        const SizedBox(height: 16),
        Container(
          padding: const EdgeInsets.fromLTRB(6, 6, 6, 10),
          decoration: BoxDecoration(
            color: scheme.surface,
            borderRadius: BorderRadius.circular(AppTokens.radiusCard),
            border: Border.all(color: scheme.outlineVariant),
          ),
          child: ApplicationFlowChart(insights: insights),
        ),
        const SizedBox(height: 16),
        Row(
          children: [
            _StatTile(label: 'Interviews', value: '$interviews'),
            const SizedBox(width: 10),
            _StatTile(label: 'Offers', value: '$offers'),
            const SizedBox(width: 10),
            _StatTile(label: 'Ghosted', value: '$ghostPct%'),
          ],
        ),
      ],
    );
  }
}

class _StatTile extends StatelessWidget {
  const _StatTile({required this.label, required this.value});
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 12),
        decoration: BoxDecoration(
          color: scheme.surfaceContainerHighest,
          borderRadius: BorderRadius.circular(14),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(value,
                style: TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.w800,
                    color: scheme.onSurface)),
            const SizedBox(height: 2),
            Text(label,
                style: TextStyle(
                    fontSize: 12.5, color: scheme.onSurfaceVariant)),
          ],
        ),
      ),
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
        Icon(Icons.insights_outlined, size: 56, color: scheme.onSurfaceVariant),
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
            'Draft an application and track its stage — your funnel from applied '
            'to offer will build up here.',
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
            Text("Couldn't load your insights",
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
