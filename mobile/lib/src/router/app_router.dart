import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/feed/feed_screen.dart';
import '../features/launch/launch_screen.dart';
import '../features/onboarding/onboarding_screen.dart';
import '../features/shell/home_shell.dart';
import '../features/shell/placeholder_tab.dart';
import '../state/session.dart';

/// App routes. Launch is the entry; the four tabs live under a persistent
/// [StatefulShellRoute] so each keeps its own navigation stack.
final routerProvider = Provider<GoRouter>((ref) {
  final refresh = _SessionRefresh(ref);
  ref.onDispose(refresh.dispose);

  return GoRouter(
    initialLocation: '/launch',
    refreshListenable: refresh,
    routes: [
      GoRoute(path: '/launch', builder: (_, _) => const LaunchScreen()),
      GoRoute(path: '/onboarding', builder: (_, _) => const OnboardingScreen()),
      StatefulShellRoute.indexedStack(
        builder: (_, _, shell) => HomeShell(shell: shell),
        branches: [
          StatefulShellBranch(routes: [
            GoRoute(path: '/feed', builder: (_, _) => const FeedScreen()),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(
                path: '/saved',
                builder: (_, _) => const PlaceholderTab(title: 'Saved')),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(
                path: '/applications',
                builder: (_, _) => const PlaceholderTab(title: 'Applications')),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(
                path: '/profile',
                builder: (_, _) => const PlaceholderTab(title: 'Profile')),
          ]),
        ],
      ),
    ],
    redirect: (context, state) {
      final session = ref.read(sessionProvider);
      final loc = state.matchedLocation;
      // Let the splash run; it routes onward itself.
      if (loc == '/launch') return null;

      final needsOnboarding =
          !(session.isSignedIn && session.onboardingComplete);
      if (needsOnboarding && loc != '/onboarding') return '/onboarding';
      if (!needsOnboarding && loc == '/onboarding') return '/feed';
      return null;
    },
  );
});

/// Bridges Riverpod session changes to go_router's [Listenable] refresh.
class _SessionRefresh extends ChangeNotifier {
  _SessionRefresh(Ref ref) {
    _sub = ref.listen<SessionState>(
      sessionProvider,
      (_, _) => notifyListeners(),
      fireImmediately: false,
    );
  }
  late final ProviderSubscription<SessionState> _sub;

  @override
  void dispose() {
    _sub.close();
    super.dispose();
  }
}
