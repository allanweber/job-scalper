import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../theme/tokens.dart';
import 'notifications_controller.dart';

/// Profile → Notifications. Toggle new-match alerts and choose the minimum
/// match score that triggers one. Backed by `/me/notifications`.
class NotificationsScreen extends ConsumerWidget {
  const NotificationsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(notificationsControllerProvider);
    final ctrl = ref.read(notificationsControllerProvider.notifier);
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(title: const Text('Notifications')),
      body: switch (state.status) {
        NotificationsStatus.loading =>
          const Center(child: CircularProgressIndicator()),
        NotificationsStatus.error => Center(
            child: Padding(
              padding: const EdgeInsets.all(32),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.cloud_off_rounded,
                      size: 48, color: scheme.onSurfaceVariant),
                  const SizedBox(height: 16),
                  Text(state.error ?? 'Something went wrong.',
                      textAlign: TextAlign.center,
                      style: TextStyle(color: scheme.onSurfaceVariant)),
                  const SizedBox(height: 20),
                  FilledButton.tonal(
                      onPressed: ctrl.refresh, child: const Text('Retry')),
                ],
              ),
            ),
          ),
        NotificationsStatus.ready => _Ready(prefs: state.prefs!, ctrl: ctrl),
      },
    );
  }
}

class _Ready extends StatelessWidget {
  const _Ready({required this.prefs, required this.ctrl});
  final dynamic prefs; // NotificationPrefs
  final NotificationsController ctrl;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final alerts = prefs.matchAlerts as bool;
    final minScore = prefs.minScore as int;

    return ListView(
      padding: const EdgeInsets.symmetric(vertical: 8),
      children: [
        SwitchListTile(
          value: alerts,
          onChanged: ctrl.setMatchAlerts,
          title: const Text('New match alerts'),
          subtitle: const Text(
              'Get a push when a new posting is a strong match for your profile.'),
        ),
        const Divider(height: 1),
        Padding(
          padding: const EdgeInsets.fromLTRB(
              AppTokens.screenPadding, 20, AppTokens.screenPadding, 4),
          child: Text('Notify me at $minScore+ match',
              style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                  color: alerts ? scheme.onSurface : scheme.onSurfaceVariant)),
        ),
        Padding(
          padding:
              const EdgeInsets.symmetric(horizontal: AppTokens.screenPadding),
          child: Text(
            'Only postings scoring at least this against your profile will '
            'notify you. Higher means fewer, stronger alerts.',
            style: TextStyle(fontSize: 12.5, color: scheme.onSurfaceVariant),
          ),
        ),
        Slider(
          value: minScore.toDouble().clamp(50, 100),
          min: 50,
          max: 100,
          divisions: 10,
          label: '$minScore',
          onChanged: alerts
              ? (v) => ctrl.setMinScore(v.round())
              : null,
        ),
      ],
    );
  }
}
