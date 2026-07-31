import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../config/env.dart';
import '../../state/session.dart';
import '../../theme/tokens.dart';

/// M1 placeholder for the onboarding flow.
///
/// The full flow (welcome slides → Google sign-in → consent → resume upload →
/// async profile build → review → boards → notifications → feed build) lands in
/// M2. For now this offers a single dev entry so Launch routing and the shell
/// are reviewable end-to-end.
class OnboardingScreen extends ConsumerStatefulWidget {
  const OnboardingScreen({super.key});

  @override
  ConsumerState<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends ConsumerState<OnboardingScreen> {
  bool _busy = false;
  String? _error;

  Future<void> _devEnter() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref.read(sessionProvider.notifier).signInWithGoogle(Env.devIdToken);
      await ref.read(sessionProvider.notifier).completeOnboarding();
      if (mounted) context.go('/feed');
    } catch (e) {
      setState(() => _error = 'Sign-in failed: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Spacer(),
              Icon(Icons.radar_rounded, size: 64, color: scheme.primary),
              const SizedBox(height: 20),
              Text('Welcome to Job Scalper',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 10),
              Text(
                'We scan remote job boards, rank roles against your resume, and '
                'draft a tailored application in one tap.',
                textAlign: TextAlign.center,
                style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 14),
              ),
              const Spacer(),
              if (_error != null) ...[
                Text(_error!,
                    style: const TextStyle(color: AppTokens.destructive, fontSize: 13)),
                const SizedBox(height: 12),
              ],
              FilledButton(
                onPressed: _busy ? null : _devEnter,
                child: _busy
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: Colors.white))
                    : const Text('Get started'),
              ),
              const SizedBox(height: 12),
              Text(
                Env.devLogin
                    ? 'Dev sign-in enabled'
                    : 'Full onboarding arrives in the next milestone',
                textAlign: TextAlign.center,
                style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 12),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
