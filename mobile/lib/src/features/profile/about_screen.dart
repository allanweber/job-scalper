import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:package_info_plus/package_info_plus.dart';

import '../../state/session.dart';
import '../onboarding/legal_text.dart';
import 'widgets/settings_tile.dart';

/// App name + version/build, loaded once from the platform.
final packageInfoProvider =
    FutureProvider<PackageInfo>((_) => PackageInfo.fromPlatform());

/// Profile → About. Legal documents, app version, and a "redo setup" shortcut.
class AboutScreen extends ConsumerWidget {
  const AboutScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    final info = ref.watch(packageInfoProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('About')),
      body: ListView(
        children: [
          const SizedBox(height: 8),
          SettingsTile(
            icon: Icons.gavel_rounded,
            title: 'Terms of Service',
            onTap: () => showLegalSheet(context, LegalKind.terms),
          ),
          SettingsTile(
            icon: Icons.privacy_tip_outlined,
            title: 'Privacy Policy',
            onTap: () => showLegalSheet(context, LegalKind.privacy),
          ),
          const Divider(height: 24),
          SettingsTile(
            icon: Icons.replay_rounded,
            title: 'Redo setup',
            subtitle: 'Replay onboarding without deleting your data',
            onTap: () => _confirmRedo(context, ref),
          ),
          const SizedBox(height: 24),
          Center(
            child: info.when(
              loading: () => const SizedBox.shrink(),
              error: (_, _) => Text('Job Scalper',
                  style: TextStyle(color: scheme.onSurfaceVariant)),
              data: (pkg) => Column(
                children: [
                  Text(pkg.appName.isEmpty ? 'Job Scalper' : pkg.appName,
                      style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                          color: scheme.onSurfaceVariant)),
                  const SizedBox(height: 2),
                  Text('Version ${pkg.version} (${pkg.buildNumber})',
                      style: TextStyle(
                          fontSize: 12.5, color: scheme.onSurfaceVariant)),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }

  Future<void> _confirmRedo(BuildContext context, WidgetRef ref) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Redo setup?'),
        content: const Text(
            'This replays the setup wizard. Your account, resume and saved '
            'jobs are kept.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Redo setup')),
        ],
      ),
    );
    if (ok == true) {
      await ref.read(sessionProvider.notifier).resetOnboarding();
    }
  }
}
