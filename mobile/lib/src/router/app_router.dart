import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../data/models/draft_models.dart';
import '../data/models/feed_models.dart';
import '../features/applications/application_insights_screen.dart';
import '../features/applications/applications_screen.dart';
import '../features/applications/draft_detail_screen.dart';
import '../features/detail/job_detail_screen.dart';
import '../features/feed/feed_screen.dart';
import '../features/launch/launch_screen.dart';
import '../features/onboarding/onboarding_screen.dart';
import '../features/profile/about_screen.dart';
import '../features/profile/appearance_screen.dart';
import '../features/profile/boards_screen.dart';
import '../features/profile/delete_account_screen.dart';
import '../features/profile/llm_key_screen.dart';
import '../features/profile/notifications_screen.dart';
import '../features/profile/profile_edit_screen.dart';
import '../features/profile/profile_screen.dart';
import '../features/profile/resume_screen.dart';
import '../features/profile/usage_screen.dart';
import '../features/saved/saved_screen.dart';
import '../features/shell/home_shell.dart';
import '../state/session.dart';

/// The `job/:id` detail sub-route shared by the Feed and Saved branches. The
/// tapped [FeedItem] is passed via `extra` so the header renders instantly.
GoRoute _jobRoute() => GoRoute(
      path: 'job/:id',
      builder: (_, state) => JobDetailScreen(
        postingId: state.pathParameters['id']!,
        initial: state.extra as FeedItem?,
      ),
    );

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
            GoRoute(
                path: '/feed',
                builder: (_, _) => const FeedScreen(),
                routes: [_jobRoute()]),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(
                path: '/saved',
                builder: (_, _) => const SavedScreen(),
                routes: [_jobRoute()]),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(
              path: '/applications',
              builder: (_, _) => const ApplicationsScreen(),
              routes: [
                GoRoute(
                  path: 'insights',
                  builder: (_, _) => const ApplicationInsightsScreen(),
                ),
                GoRoute(
                  path: 'draft/:id',
                  builder: (_, state) => DraftDetailScreen(
                    draftId: state.pathParameters['id']!,
                    initial: state.extra as DraftSummary?,
                  ),
                  // Distinct param name: go_router rejects a nested route that
                  // repeats a parent's parameter name (both `:id`), so the job
                  // detail reached from a draft uses `:postingId`.
                  routes: [
                    GoRoute(
                      path: 'job/:postingId',
                      builder: (_, state) => JobDetailScreen(
                        postingId: state.pathParameters['postingId']!,
                        initial: state.extra as FeedItem?,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(
              path: '/profile',
              builder: (_, _) => const ProfileScreen(),
              routes: [
                GoRoute(
                    path: 'edit',
                    builder: (_, _) => const ProfileEditScreen()),
                GoRoute(
                    path: 'resume', builder: (_, _) => const ResumeScreen()),
                GoRoute(
                    path: 'boards', builder: (_, _) => const BoardsScreen()),
                GoRoute(path: 'key', builder: (_, _) => const LlmKeyScreen()),
                GoRoute(path: 'usage', builder: (_, _) => const UsageScreen()),
                GoRoute(
                    path: 'notifications',
                    builder: (_, _) => const NotificationsScreen()),
                GoRoute(
                    path: 'appearance',
                    builder: (_, _) => const AppearanceScreen()),
                GoRoute(path: 'about', builder: (_, _) => const AboutScreen()),
                GoRoute(
                    path: 'delete',
                    builder: (_, _) => const DeleteAccountScreen()),
              ],
            ),
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
