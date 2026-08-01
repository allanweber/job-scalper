import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/account_repository.dart';
import '../../data/models/account_models.dart';
import '../../data/providers.dart';
import '../../state/session.dart';

/// The linear onboarding steps, in order. The flow renders one at a time and
/// advances through [OnboardingController.next] / [back].
enum OnboardingStep {
  welcome,
  signIn,
  consent,
  resume,
  buildingProfile,
  reviewProfile,
  boards,
  notifications,
  buildingFeed,
}

/// Status of a staged async operation (profile build, feed build).
enum AsyncPhase { idle, running, done, failed }

@immutable
class OnboardingState {
  const OnboardingState({
    this.step = OnboardingStep.welcome,
    this.busy = false,
    this.error,
    this.resume,
    this.profile = const Profile(),
    this.sources,
    this.notificationsEnabled = false,
    this.buildPhase = AsyncPhase.idle,
    this.buildStepIndex = 0,
  });

  final OnboardingStep step;

  /// A short synchronous action (sign-in, consent, saving) is in flight.
  final bool busy;
  final String? error;

  final ResumeInfo? resume;
  final Profile profile;
  final SourcesInfo? sources;
  final bool notificationsEnabled;

  /// Drives both async loaders (profile build on [OnboardingStep.buildingProfile],
  /// feed build on [OnboardingStep.buildingFeed]).
  final AsyncPhase buildPhase;
  final int buildStepIndex;

  bool get hasResume => resume != null;

  OnboardingState copyWith({
    OnboardingStep? step,
    bool? busy,
    Object? error = _noChange,
    Object? resume = _noChange,
    Profile? profile,
    Object? sources = _noChange,
    bool? notificationsEnabled,
    AsyncPhase? buildPhase,
    int? buildStepIndex,
  }) =>
      OnboardingState(
        step: step ?? this.step,
        busy: busy ?? this.busy,
        error: error == _noChange ? this.error : error as String?,
        resume: resume == _noChange ? this.resume : resume as ResumeInfo?,
        profile: profile ?? this.profile,
        sources: sources == _noChange ? this.sources : sources as SourcesInfo?,
        notificationsEnabled: notificationsEnabled ?? this.notificationsEnabled,
        buildPhase: buildPhase ?? this.buildPhase,
        buildStepIndex: buildStepIndex ?? this.buildStepIndex,
      );

  static const _noChange = Object();
}

/// Orchestrates the onboarding flow: owns the step cursor and the data collected
/// along the way, and commits each step to the backend as the user advances.
class OnboardingController extends Notifier<OnboardingState> {
  AccountRepository get _account => ref.read(accountRepositoryProvider);
  SessionController get _session => ref.read(sessionProvider.notifier);

  /// Minimum wall-clock time each async loader stays visible, so a backend that
  /// finishes instantly (inline job queue) still reads as a staged build.
  static const _minBuild = Duration(milliseconds: 2600);
  static const _pollEvery = Duration(milliseconds: 500);
  static const _pollTimeout = Duration(seconds: 40);

  @override
  OnboardingState build() => const OnboardingState();

  void _go(OnboardingStep step) =>
      state = state.copyWith(step: step, error: null);

  // -- welcome / sign-in / consent ------------------------------------------

  void startFromWelcome() => _go(OnboardingStep.signIn);

  /// Continue with Google. Runs native Google Sign-In (or the dev stand-in),
  /// exchanges the returned ID token for an app session, then advances — to
  /// consent, or straight to resume for a returning user who already accepted.
  Future<void> signIn() => _guard(() async {
        final idToken =
            await ref.read(googleAuthenticatorProvider).obtainIdToken();
        if (idToken == null) return; // user cancelled
        await _session.signInWithGoogle(idToken);
        final user = ref.read(sessionProvider).user;
        _go(user?.legalAccepted == true
            ? OnboardingStep.resume
            : OnboardingStep.consent);
      });

  Future<void> acceptConsent() => _guard(() async {
        final user = await _account.acceptLegal();
        _session.updateUser(user);
        _go(OnboardingStep.resume);
      });

  // -- resume ---------------------------------------------------------------

  /// Upload the picked resume bytes, then advance to the async profile build.
  Future<void> submitResume({
    required List<int> bytes,
    required String filename,
    String? contentType,
  }) =>
      _guard(() async {
        final info = await _account.uploadResume(
            bytes: bytes, filename: filename, contentType: contentType);
        state = state.copyWith(resume: info);
        _go(OnboardingStep.buildingProfile);
        await _buildProfile();
      });

  Future<void> _buildProfile() async {
    state = state.copyWith(buildPhase: AsyncPhase.running, buildStepIndex: 0);
    final ticker = _startTicker(3);
    final started = DateTime.now();

    // Run the async build, capturing whether it failed and why. A failed build
    // (or a poll timeout) isn't fatal: we still drop the user on the review step
    // so they can fill the profile in by hand — but we surface the real reason.
    var failed = false;
    String? reason;
    try {
      final jobId = await _account.buildProfileFromResume();
      final job = await _pollJob(jobId);
      failed = job.isFailed;
      reason = job.error;
    } catch (e) {
      failed = true;
      reason = _humanize(e);
    }

    // Load whatever profile exists. On failure the backend created none, so
    // GET /me/profile 404s (repo returns null) — keep the empty default.
    var profile = const Profile();
    try {
      profile = await _account.getProfile();
    } catch (_) {/* no profile built; keep the empty default */}

    await _settle(started);
    ticker.cancel();
    // Advance to review and set the error in one update: _go() clears error, so
    // navigating separately would wipe the failure message before it's seen.
    state = state.copyWith(
      step: OnboardingStep.reviewProfile,
      profile: profile,
      buildPhase: failed ? AsyncPhase.failed : AsyncPhase.done,
      buildStepIndex: 3,
      error: failed ? _profileBuildError(reason) : null,
    );
  }

  /// A human-facing message for a failed resume-driven profile build, folding in
  /// the backend job's own error so it's obvious what went wrong.
  String _profileBuildError(String? raw) {
    final e = (raw ?? '').trim();
    if (e.startsWith('quota_exceeded')) {
      return 'You’ve used all your automatic profile builds for this period. '
          'Fill in your profile below — you can always edit it later.';
    }
    if (e.isEmpty) {
      return 'We couldn’t build your profile automatically. '
          'Fill it in below — you can edit it anytime.';
    }
    return 'We couldn’t read your resume automatically ($e). '
        'Fill in your profile below.';
  }

  // -- review profile -------------------------------------------------------

  void updateProfile(Profile profile) => state = state.copyWith(profile: profile);

  Future<void> saveProfileAndContinue() => _guard(() async {
        final saved = await _account.saveProfile(state.profile);
        state = state.copyWith(profile: saved);
        await _loadSources();
        _go(OnboardingStep.boards);
      });

  // -- boards ---------------------------------------------------------------

  Future<void> _loadSources() async {
    final s = await _account.getSources();
    // Default to the first up-to-max boards if the user has none selected yet.
    final selected = s.selected.isNotEmpty
        ? s.selected
        : s.available.take(s.maxAllowed).toList();
    state = state.copyWith(
        sources: SourcesInfo(
            selected: selected, available: s.available, maxAllowed: s.maxAllowed));
  }

  /// Toggle a board, respecting the plan cap. Returns false if the tap was
  /// blocked by the cap (so the UI can surface a toast).
  bool toggleBoard(String id) {
    final s = state.sources;
    if (s == null) return false;
    final sel = [...s.selected];
    if (sel.contains(id)) {
      sel.remove(id);
    } else {
      if (sel.length >= s.maxAllowed) return false;
      sel.add(id);
    }
    state = state.copyWith(
        sources: SourcesInfo(
            selected: sel, available: s.available, maxAllowed: s.maxAllowed));
    return true;
  }

  Future<void> saveBoardsAndContinue() => _guard(() async {
        final s = state.sources;
        if (s != null) {
          final saved = await _account.saveSources(s.selected);
          state = state.copyWith(sources: saved);
        }
        _go(OnboardingStep.notifications);
      });

  // -- notifications --------------------------------------------------------

  void setNotifications(bool enabled) {
    state = state.copyWith(notificationsEnabled: enabled);
    _go(OnboardingStep.buildingFeed);
    _buildFeed();
  }

  Future<void> _buildFeed() async {
    state = state.copyWith(buildPhase: AsyncPhase.running, buildStepIndex: 0);
    final ticker = _startTicker(3);
    final started = DateTime.now();
    await _settle(started);
    ticker.cancel();
    state = state.copyWith(buildPhase: AsyncPhase.done, buildStepIndex: 3);
    await _session.completeOnboarding();
  }

  // -- navigation -----------------------------------------------------------

  void back() {
    const order = OnboardingStep.values;
    // The async build steps only make sense while their build is running: they
    // have nothing to re-trigger them and can't be stepped back from.
    if (state.step == OnboardingStep.buildingProfile ||
        state.step == OnboardingStep.buildingFeed) {
      return;
    }
    // Step back, skipping over any async build step so e.g. Review -> back lands
    // on Resume (not on the finished "Building your profile" loader, which would
    // strand the user with no way forward or back).
    var i = order.indexOf(state.step) - 1;
    while (i > 0 &&
        (order[i] == OnboardingStep.buildingProfile ||
            order[i] == OnboardingStep.buildingFeed)) {
      i--;
    }
    if (i < 0) return;
    _go(order[i]);
  }

  // -- helpers --------------------------------------------------------------

  /// Runs a short async action with busy/error bookkeeping.
  Future<void> _guard(Future<void> Function() action) async {
    state = state.copyWith(busy: true, error: null);
    try {
      await action();
    } catch (e) {
      state = state.copyWith(error: _humanize(e));
    } finally {
      state = state.copyWith(busy: false);
    }
  }

  /// Advances the visible step index of a staged loader on a timer (cosmetic).
  Timer _startTicker(int steps) => Timer.periodic(
        Duration(milliseconds: (_minBuild.inMilliseconds / (steps + 1)).round()),
        (t) {
          if (state.buildStepIndex >= steps) {
            t.cancel();
            return;
          }
          state = state.copyWith(buildStepIndex: state.buildStepIndex + 1);
        },
      );

  Future<void> _settle(DateTime started) async {
    final elapsed = DateTime.now().difference(started);
    if (elapsed < _minBuild) await Future.delayed(_minBuild - elapsed);
  }

  Future<JobRecord> _pollJob(String jobId) async {
    final deadline = DateTime.now().add(_pollTimeout);
    while (DateTime.now().isBefore(deadline)) {
      final job = await _account.getJob(jobId);
      if (job.isDone) return job;
      await Future.delayed(_pollEvery);
    }
    throw TimeoutException('Profile build timed out');
  }

  String _humanize(Object e) {
    final s = e.toString();
    return s.startsWith('Exception: ') ? s.substring(11) : s;
  }
}

final onboardingControllerProvider =
    NotifierProvider<OnboardingController, OnboardingState>(
        OnboardingController.new);
