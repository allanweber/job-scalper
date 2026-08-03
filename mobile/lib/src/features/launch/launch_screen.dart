import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../state/session.dart';
import '../../theme/tokens.dart';

/// Branded splash. Shows for ~1.6s while the session is restored, then routes
/// to Onboarding (first run / signed out) or Feed (returning user).
class LaunchScreen extends ConsumerStatefulWidget {
  const LaunchScreen({super.key});

  @override
  ConsumerState<LaunchScreen> createState() => _LaunchScreenState();
}

class _LaunchScreenState extends ConsumerState<LaunchScreen> {
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    // A restored session persists only the tokens, so hydrate the user from the
    // server while the splash shows — the profile header/footer then have real
    // details instead of placeholders.
    final s = ref.read(sessionProvider);
    if (s.isSignedIn && s.user == null) {
      ref.read(sessionProvider.notifier).refreshUser();
    }
    _timer = Timer(const Duration(milliseconds: 1600), _go);
  }

  void _go() {
    if (!mounted) return;
    final s = ref.read(sessionProvider);
    final target = (s.isSignedIn && s.onboardingComplete) ? '/feed' : '/onboarding';
    context.go(target);
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final restoring = ref.watch(sessionProvider).isSignedIn;
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [AppTokens.brandPrimary, AppTokens.brandDeep],
          ),
        ),
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _Glyph(),
              const SizedBox(height: 22),
              const Text('Job Scalper',
                  style: TextStyle(
                      color: Colors.white,
                      fontSize: 26,
                      fontWeight: FontWeight.w900,
                      letterSpacing: -0.2)),
              const SizedBox(height: 28),
              const SizedBox(
                width: 26,
                height: 26,
                child: CircularProgressIndicator(
                    strokeWidth: 2.5,
                    valueColor: AlwaysStoppedAnimation(Colors.white70)),
              ),
              const SizedBox(height: 16),
              Text(restoring ? 'Restoring your session…' : 'Warming up…',
                  style: const TextStyle(color: Colors.white70, fontSize: 13)),
            ],
          ),
        ),
      ),
    );
  }
}

class _Glyph extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    // The app glyph (mint magnifier on brand teal), shown in a soft ring.
    return Container(
      padding: const EdgeInsets.all(6),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.10),
        shape: BoxShape.circle,
        border: Border.all(color: Colors.white24),
      ),
      child: Image.asset('assets/brand/icon-circle.png',
          width: 104, height: 104, fit: BoxFit.contain),
    );
  }
}
