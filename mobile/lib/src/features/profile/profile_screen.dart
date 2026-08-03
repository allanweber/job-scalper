import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../state/push_registration.dart';
import '../../state/session.dart';
import 'widgets/settings_tile.dart';

/// The Profile tab root: an account header plus a settings-style list. Each row
/// pushes a focused sub-screen under `/profile/...`.
class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(sessionProvider).user;
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(title: const Text('Profile')),
      body: ListView(
        children: [
          _Header(
            name: user?.displayName ?? user?.email ?? 'Your account',
            email: user?.email ?? '',
            avatarUrl: user?.avatarUrl,
            plan: user?.plan ?? 'free',
          ),
          const SizedBox(height: 8),
          _SectionLabel('Job matching'),
          SettingsTile(
            icon: Icons.tune_rounded,
            title: 'Search profile',
            subtitle: 'Titles, skills, keywords and salary we rank against',
            onTap: () => context.push('/profile/edit'),
          ),
          SettingsTile(
            icon: Icons.description_outlined,
            title: 'Resume',
            subtitle: 'Replace your resume or rebuild your profile from it',
            onTap: () => context.push('/profile/resume'),
          ),
          SettingsTile(
            icon: Icons.travel_explore_rounded,
            title: 'Job boards',
            subtitle: 'Choose which boards we scan for you',
            onTap: () => context.push('/profile/boards'),
          ),
          const SizedBox(height: 8),
          _SectionLabel('Plan & AI'),
          SettingsTile(
            icon: Icons.key_rounded,
            title: 'Your API key',
            subtitle: 'Use your own Anthropic or OpenAI key',
            onTap: () => context.push('/profile/key'),
          ),
          SettingsTile(
            icon: Icons.bar_chart_rounded,
            title: 'Usage',
            subtitle: 'This period\'s usage against your plan limits',
            onTap: () => context.push('/profile/usage'),
          ),
          const SizedBox(height: 8),
          _SectionLabel('App'),
          SettingsTile(
            icon: Icons.notifications_none_rounded,
            title: 'Notifications',
            subtitle: 'New-match alerts and threshold',
            onTap: () => context.push('/profile/notifications'),
          ),
          SettingsTile(
            icon: Icons.palette_outlined,
            title: 'Appearance',
            subtitle: 'Light, dark or system theme',
            onTap: () => context.push('/profile/appearance'),
          ),
          SettingsTile(
            icon: Icons.info_outline_rounded,
            title: 'About',
            subtitle: 'Legal, version and setup',
            onTap: () => context.push('/profile/about'),
          ),
          const SizedBox(height: 16),
          SettingsTile(
            icon: Icons.logout_rounded,
            title: 'Sign out',
            onTap: () => _confirmSignOut(context, ref),
          ),
          SettingsTile(
            icon: Icons.delete_outline_rounded,
            title: 'Delete account',
            danger: true,
            onTap: () => context.push('/profile/delete'),
          ),
          if ((user?.email ?? '').isNotEmpty) ...[
            const SizedBox(height: 24),
            Center(
              child: Text('Signed in as ${user!.email}',
                  style:
                      TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
            ),
          ],
          const SizedBox(height: 24),
        ],
      ),
    );
  }

  Future<void> _confirmSignOut(BuildContext context, WidgetRef ref) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Sign out?'),
        content: const Text('You can sign back in with Google any time.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Sign out')),
        ],
      ),
    );
    if (ok == true) {
      // Drop this device's push token first, while the session is still
      // authorized to make the request.
      await ref.read(pushRegistrationProvider.notifier).unregisterCurrent();
      await ref.read(sessionProvider.notifier).signOut();
    }
  }
}

class _Header extends StatelessWidget {
  const _Header({
    required this.name,
    required this.email,
    required this.avatarUrl,
    required this.plan,
  });

  final String name;
  final String email;
  final String? avatarUrl;
  final String plan;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final initial = name.isNotEmpty ? name[0].toUpperCase() : '?';
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 20, 20, 12),
      child: Row(
        children: [
          CircleAvatar(
            radius: 30,
            backgroundColor: scheme.primaryContainer,
            foregroundImage: (avatarUrl != null && avatarUrl!.isNotEmpty)
                ? NetworkImage(avatarUrl!)
                : null,
            child: Text(initial,
                style: TextStyle(
                    fontSize: 24,
                    fontWeight: FontWeight.w700,
                    color: scheme.onPrimaryContainer)),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name,
                    style: const TextStyle(
                        fontSize: 18, fontWeight: FontWeight.w700),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis),
                if (email.isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text(email,
                      style:
                          TextStyle(fontSize: 13, color: scheme.onSurfaceVariant),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis),
                ],
                const SizedBox(height: 8),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
                  decoration: BoxDecoration(
                    color: scheme.secondaryContainer,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Text('${plan.toUpperCase()} PLAN',
                      style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 0.5,
                          color: scheme.onSecondaryContainer)),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SectionLabel extends StatelessWidget {
  const _SectionLabel(this.text);
  final String text;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 12, 20, 6),
      child: Text(text.toUpperCase(),
          style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.6,
              color: scheme.primary)),
    );
  }
}
