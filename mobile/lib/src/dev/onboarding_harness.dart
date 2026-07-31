import '../data/account_repository.dart';
import '../data/google_authenticator.dart';
import '../data/models/account_models.dart';
import '../data/models/api_models.dart';
import '../features/onboarding/onboarding_controller.dart';

/// Dev/QA-only support (NOT used by `main.dart`): an in-memory account backend
/// and a pre-seedable onboarding controller. Shared by the widget tests and the
/// screenshot entrypoint so both exercise the real flow logic without a server.

const demoProfile = Profile(
  id: 'p1',
  origin: 'resume',
  titles: ['Backend Engineer', 'Platform Engineer'],
  requiredSkills: ['Python', 'PostgreSQL', 'AWS', 'Docker'],
  niceToHaveSkills: ['Kubernetes', 'Go', 'Terraform'],
  keywords: ['fintech', 'API', 'microservices'],
  excludeKeywords: ['senior manager', 'on-site'],
  remoteOnly: true,
  salaryFloor: 120000,
);

const _availableBoards = [
  'remotive',
  'remoteok',
  'weworkremotely',
  'arbeitnow',
  'jobicy',
  'himalayas',
  'workingnomads',
  'themuse',
];

const demoSources = SourcesInfo(
  selected: ['remotive', 'weworkremotely'],
  available: _availableBoards,
  maxAllowed: 3,
);

final demoResume = ResumeInfo(
  filename: 'alex_weber_resume.pdf',
  contentType: 'application/pdf',
  sizeBytes: 184320,
  textChars: 5120,
  updatedAt: DateTime(2026, 7, 30).toIso8601String(),
);

ApiUser _demoUser({bool legal = true}) => ApiUser(
      id: 'u1',
      email: 'alex@example.com',
      displayName: 'Alex Weber',
      plan: 'free',
      tosAccepted: legal,
      privacyAccepted: legal,
    );

/// In-memory [AccountRepository]. Records the last saved profile/sources so
/// tests can assert what was persisted; every async call resolves immediately.
class FakeAccountRepository implements AccountRepository {
  FakeAccountRepository({
    this.builtProfile = demoProfile,
    this.jobFails = false,
  }) : _profile = const Profile();

  final Profile builtProfile;
  final bool jobFails;

  Profile _profile;
  SourcesInfo _sources = const SourcesInfo(
      selected: [], available: _availableBoards, maxAllowed: 3);

  Profile? savedProfile;
  List<String>? savedSources;
  bool legalAccepted = false;
  int resumeUploads = 0;

  @override
  Future<ApiUser> acceptLegal() async {
    legalAccepted = true;
    return _demoUser(legal: true);
  }

  @override
  Future<Profile> getProfile() async => _profile;

  @override
  Future<Profile> saveProfile(Profile profile) async {
    savedProfile = profile;
    _profile = profile.copyWith(id: 'p1', origin: 'user');
    return _profile;
  }

  @override
  Future<String> buildProfileFromResume() async => 'job-1';

  @override
  Future<ResumeInfo> uploadResume({
    required List<int> bytes,
    required String filename,
    String? contentType,
  }) async {
    resumeUploads++;
    return ResumeInfo(
      filename: filename,
      contentType: contentType,
      sizeBytes: bytes.length,
      textChars: bytes.length,
      updatedAt: DateTime(2026, 7, 31).toIso8601String(),
    );
  }

  @override
  Future<ResumeInfo?> getResume() async => null;

  @override
  Future<SourcesInfo> getSources() async => _sources;

  @override
  Future<SourcesInfo> saveSources(List<String> sources) async {
    savedSources = sources;
    _sources = SourcesInfo(
        selected: sources,
        available: _sources.available,
        maxAllowed: _sources.maxAllowed);
    return _sources;
  }

  @override
  Future<JobRecord> getJob(String jobId) async {
    // On success, publish the built profile so the review step is pre-filled.
    if (!jobFails) _profile = builtProfile;
    return JobRecord(
      id: jobId,
      kind: 'profile_from_resume',
      status: jobFails ? 'failed' : 'finished',
      error: jobFails ? 'unreadable resume' : null,
    );
  }
}

/// A [GoogleAuthenticator] that returns a canned token (or null to simulate a
/// cancelled sign-in) without touching the platform.
class FakeGoogleAuthenticator implements GoogleAuthenticator {
  FakeGoogleAuthenticator({this.token = 'fake-id-token'});
  final String? token;

  @override
  Future<String?> obtainIdToken() async => token;
}

/// An [OnboardingController] pre-positioned on a given step with seeded data —
/// used by the screenshot harness (and smoke tests) to render any step directly.
class SeededOnboardingController extends OnboardingController {
  SeededOnboardingController(this._seed);
  final OnboardingState _seed;

  @override
  OnboardingState build() => _seed;
}

/// Seeded states for each screenshot frame.
OnboardingState seededState(OnboardingStep step) => switch (step) {
      OnboardingStep.reviewProfile =>
        OnboardingState(step: step, profile: demoProfile),
      OnboardingStep.boards => OnboardingState(step: step, sources: demoSources),
      OnboardingStep.buildingProfile => OnboardingState(
          step: step, buildPhase: AsyncPhase.running, buildStepIndex: 1),
      OnboardingStep.buildingFeed => OnboardingState(
          step: step, buildPhase: AsyncPhase.running, buildStepIndex: 2),
      _ => OnboardingState(step: step),
    };
