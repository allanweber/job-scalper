import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'src/app.dart';
import 'src/data/models/account_models.dart';
import 'src/data/models/draft_models.dart';
import 'src/data/providers.dart';
import 'src/dev/drafts_harness.dart';
import 'src/dev/feed_harness.dart';
import 'src/dev/onboarding_harness.dart';
import 'src/state/session.dart';

/// Portfolio/screenshot entrypoint (NOT shipped). Seeds a signed-in session AND
/// overrides every repository with the in-memory demo fakes, so every screen —
/// feed, job detail, drafts, insights, profile — renders fully populated with no
/// backend. Theme follows the platform brightness, so a viewer can screenshot
/// light and dark by toggling prefers-color-scheme.
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  await prefs.setBool('session.onboardingComplete', true);
  await prefs.setInt('session.themeMode', ThemeMode.system.index);
  await prefs.setString('session.tokens',
      '{"access_token":"demo","refresh_token":"demo","expires_in":900}');

  runApp(
    ProviderScope(
      overrides: [
        sharedPrefsProvider.overrideWithValue(prefs),
        accountRepositoryProvider
            .overrideWithValue(_PortfolioAccountRepository()),
        feedRepositoryProvider.overrideWithValue(FakeFeedRepository()),
        draftsRepositoryProvider.overrideWithValue(FakeDraftsRepository(
          items: _portfolioDrafts,
          insights: const ApplicationInsights(
            total: 24,
            counts: {
              'applied': 6,
              'interviewing': 8,
              'offer': 3,
              'rejected': 5,
              'ghosted': 2,
            },
          ),
        )),
      ],
      child: const JobScalperApp(),
    ),
  );
}

/// A richer set of applications than the shared harness default, so the
/// Applications list shows a spread of stages and the funnel looks real.
final _portfolioDrafts = <DraftSummary>[
  DraftSummary(
    id: 'd1', postingId: 'j1', jobSource: 'pool', keySource: 'platform',
    createdAt: DateTime.now().subtract(const Duration(hours: 2)).toIso8601String(),
    title: 'Senior Backend Engineer', company: 'Linear',
    url: 'https://example.com/jobs/j1',
    applied: true, applicationStatus: 'interviewing',
  ),
  DraftSummary(
    id: 'd2', postingId: 'j2', jobSource: 'pool', keySource: 'byo',
    createdAt: DateTime.now().subtract(const Duration(days: 1)).toIso8601String(),
    title: 'Platform Engineer, Payments', company: 'Stripe',
    url: 'https://example.com/jobs/j2',
    applied: true, applicationStatus: 'offer',
  ),
  DraftSummary(
    id: 'd3', postingId: 'j3', jobSource: 'pool', keySource: 'platform',
    createdAt: DateTime.now().subtract(const Duration(days: 4)).toIso8601String(),
    title: 'Backend Developer (Django)', company: 'Arbeitnow GmbH',
    url: 'https://example.com/jobs/j3',
    applied: true, applicationStatus: 'applied',
  ),
  DraftSummary(
    id: 'd4', postingId: 'j4', jobSource: 'pool', keySource: 'platform',
    createdAt: DateTime.now().subtract(const Duration(minutes: 40)).toIso8601String(),
    title: 'Full-Stack Engineer', company: 'Nomad Labs',
    url: 'https://example.com/jobs/j4',
    status: 'pending',
  ),
];

/// [FakeAccountRepository] pre-populated so the profile, résumé, boards, and LLM
/// key screens all render with real-looking content.
class _PortfolioAccountRepository extends FakeAccountRepository {
  @override
  Future<Profile> getProfile() async => demoProfile;

  @override
  Future<ResumeInfo?> getResume() async => demoResume;

  @override
  Future<SourcesInfo> getSources() async => demoSources;

  @override
  Future<LlmKeysInfo> getKeys() async => LlmKeysInfo(keys: [
        LlmKeyInfo(
          provider: 'anthropic',
          valid: true,
          lastValidatedAt: DateTime(2026, 8, 1).toIso8601String(),
        ),
      ]);
}
