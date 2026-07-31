import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../onboarding_controller.dart';

/// Step 9 — notifications opt-in. Allow / Not now; either advances to the feed
/// build. (Real OS permission prompting is wired on device; here we just record
/// the preference.)
class NotificationsStep extends ConsumerWidget {
  const NotificationsStep({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    final ctrl = ref.read(onboardingControllerProvider.notifier);
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Align(
                alignment: Alignment.centerLeft,
                child: IconButton(
                  onPressed: ctrl.back,
                  icon: const Icon(Icons.arrow_back),
                ),
              ),
              const Spacer(),
              Center(
                child: Container(
                  width: 120,
                  height: 120,
                  decoration: BoxDecoration(
                      color: scheme.primaryContainer, shape: BoxShape.circle),
                  child: Icon(Icons.notifications_active_rounded,
                      size: 56, color: scheme.onPrimaryContainer),
                ),
              ),
              const SizedBox(height: 32),
              Text('Never miss a strong match',
                  textAlign: TextAlign.center,
                  style: Theme.of(context)
                      .textTheme
                      .headlineSmall
                      ?.copyWith(fontWeight: FontWeight.w800)),
              const SizedBox(height: 12),
              Text(
                'Get a heads-up when a new posting scores 90+ against your '
                'profile. No spam — only the roles worth your time.',
                textAlign: TextAlign.center,
                style: TextStyle(
                    color: scheme.onSurfaceVariant, fontSize: 15, height: 1.5),
              ),
              const Spacer(),
              SizedBox(
                height: 52,
                child: FilledButton(
                  onPressed: () => ctrl.setNotifications(true),
                  child: const Text('Allow notifications',
                      style:
                          TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
                ),
              ),
              const SizedBox(height: 8),
              TextButton(
                onPressed: () => ctrl.setNotifications(false),
                child: const Text('Not now'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
