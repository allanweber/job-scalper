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
            colors: [AppTokens.brandPrimary, Color(0xFF00463C)],
          ),
        ),
        child: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _Glyph(),
              const SizedBox(height: 20),
              const Text('Job Scalper',
                  style: TextStyle(
                      color: Colors.white,
                      fontSize: 24,
                      fontWeight: FontWeight.w700)),
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
    return Container(
      width: 84,
      height: 84,
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.16),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: Colors.white24),
      ),
      child: const Icon(Icons.radar_rounded, color: Colors.white, size: 44),
    );
  }
}
