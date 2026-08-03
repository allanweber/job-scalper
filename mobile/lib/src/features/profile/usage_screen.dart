import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/account_models.dart';
import '../../data/providers.dart';

/// Current-period usage against plan limits (`GET /me/quota`). Auto-disposed so
/// it re-fetches each time the screen is opened.
final quotaProvider = FutureProvider.autoDispose<QuotaInfo>(
    (ref) => ref.watch(accountRepositoryProvider).getQuota());

/// Human labels for the known quota metric keys; unknown keys are title-cased.
String _metricLabel(String metric) => switch (metric) {
      'profile_builds' => 'Profile rebuilds',
      'drafts' => 'Application drafts',
      'feed_refreshes' => 'Feed refreshes',
      _ => metric
          .split('_')
          .where((w) => w.isNotEmpty)
          .map((w) => w[0].toUpperCase() + w.substring(1))
          .join(' '),
    };

class UsageScreen extends ConsumerWidget {
  const UsageScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(quotaProvider);
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(title: const Text('Usage')),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => _ErrorBody(onRetry: () => ref.invalidate(quotaProvider)),
        data: (quota) => ListView(
          padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
          children: [
            Row(
              children: [
                Text('${quota.plan.toUpperCase()} plan',
                    style: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.w700)),
                const Spacer(),
                if (quota.period.isNotEmpty)
                  Text(quota.period,
                      style: TextStyle(
                          fontSize: 13, color: scheme.onSurfaceVariant)),
              ],
            ),
            const SizedBox(height: 4),
            if (quota.byoKey)
              _ByoBanner(scheme: scheme)
            else
              Text('Limits reset each period.',
                  style:
                      TextStyle(fontSize: 13, color: scheme.onSurfaceVariant)),
            const SizedBox(height: 16),
            for (final m in quota.metrics) _MetricRow(metric: m),
            if (quota.metrics.isEmpty) ...[
              const SizedBox(height: 24),
              Center(
                child: Text('No usage recorded yet.',
                    style: TextStyle(color: scheme.onSurfaceVariant)),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _ByoBanner extends StatelessWidget {
  const _ByoBanner({required this.scheme});
  final ColorScheme scheme;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: scheme.primaryContainer,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        children: [
          Icon(Icons.all_inclusive_rounded,
              size: 18, color: scheme.onPrimaryContainer),
          const SizedBox(width: 8),
          Expanded(
            child: Text('Unlimited — running on your own API key.',
                style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: scheme.onPrimaryContainer)),
          ),
        ],
      ),
    );
  }
}

class _MetricRow extends StatelessWidget {
  const _MetricRow({required this.metric});
  final QuotaMetricInfo metric;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final unlimited = metric.unlimited;
    final fraction = (unlimited || metric.limit <= 0)
        ? 0.0
        : (metric.used / metric.limit).clamp(0.0, 1.0);
    final valueText =
        unlimited ? '${metric.used} used' : '${metric.used} / ${metric.limit}';

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(_metricLabel(metric.metric),
                    style: const TextStyle(
                        fontSize: 14.5, fontWeight: FontWeight.w600)),
              ),
              Text(valueText,
                  style: TextStyle(
                      fontSize: 13,
                      fontFamily: 'RobotoMono',
                      color: scheme.onSurfaceVariant)),
            ],
          ),
          const SizedBox(height: 6),
          if (!unlimited)
            ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: LinearProgressIndicator(
                value: fraction,
                minHeight: 6,
                backgroundColor: scheme.surfaceContainerHighest,
              ),
            ),
        ],
      ),
    );
  }
}

class _ErrorBody extends StatelessWidget {
  const _ErrorBody({required this.onRetry});
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text('Could not load your usage.'),
          const SizedBox(height: 12),
          FilledButton.tonal(onPressed: onRetry, child: const Text('Retry')),
        ],
      ),
    );
  }
}
