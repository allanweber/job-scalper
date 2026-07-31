import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../onboarding_controller.dart';

class _Slide {
  const _Slide(this.icon, this.title, this.body);
  final IconData icon;
  final String title;
  final String body;
}

const _slides = <_Slide>[
  _Slide(Icons.travel_explore_rounded, 'Remote roles, already ranked',
      'We continuously scan remote job boards so your feed is always ready — no searching, no refreshing.'),
  _Slide(Icons.insights_rounded, 'Scored against your resume',
      'Every posting gets a 0–100 match score from your real skills, keywords, and salary floor.'),
  _Slide(Icons.auto_awesome_rounded, 'A tailored application in one tap',
      'Generate a resume and cover letter grounded in your experience, ready to send.'),
];

/// Step 1 — three swipeable value-prop slides with a dot pager. "Skip" shows
/// only on the first slide; the last slide's CTA reads "Get started".
class WelcomeStep extends ConsumerStatefulWidget {
  const WelcomeStep({super.key});

  @override
  ConsumerState<WelcomeStep> createState() => _WelcomeStepState();
}

class _WelcomeStepState extends ConsumerState<WelcomeStep> {
  final _pager = PageController();
  int _page = 0;

  @override
  void dispose() {
    _pager.dispose();
    super.dispose();
  }

  void _next() {
    if (_page < _slides.length - 1) {
      _pager.nextPage(
          duration: const Duration(milliseconds: 280), curve: Curves.easeOut);
    } else {
      ref.read(onboardingControllerProvider.notifier).startFromWelcome();
    }
  }

  void _skip() =>
      ref.read(onboardingControllerProvider.notifier).startFromWelcome();

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final isLast = _page == _slides.length - 1;
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            Align(
              alignment: Alignment.centerRight,
              child: AnimatedOpacity(
                opacity: _page == 0 ? 1 : 0,
                duration: const Duration(milliseconds: 150),
                child: TextButton(
                  onPressed: _page == 0 ? _skip : null,
                  child: const Text('Skip'),
                ),
              ),
            ),
            Expanded(
              child: PageView.builder(
                controller: _pager,
                onPageChanged: (i) => setState(() => _page = i),
                itemCount: _slides.length,
                itemBuilder: (_, i) {
                  final s = _slides[i];
                  return Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 32),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Container(
                          width: 120,
                          height: 120,
                          decoration: BoxDecoration(
                            color: scheme.primaryContainer,
                            shape: BoxShape.circle,
                          ),
                          child: Icon(s.icon,
                              size: 56, color: scheme.onPrimaryContainer),
                        ),
                        const SizedBox(height: 36),
                        Text(s.title,
                            textAlign: TextAlign.center,
                            style: Theme.of(context)
                                .textTheme
                                .headlineSmall
                                ?.copyWith(fontWeight: FontWeight.w800)),
                        const SizedBox(height: 14),
                        Text(s.body,
                            textAlign: TextAlign.center,
                            style: TextStyle(
                                color: scheme.onSurfaceVariant,
                                fontSize: 15,
                                height: 1.5)),
                      ],
                    ),
                  );
                },
              ),
            ),
            const SizedBox(height: 16),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                for (var i = 0; i < _slides.length; i++)
                  AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    margin: const EdgeInsets.symmetric(horizontal: 4),
                    width: i == _page ? 22 : 8,
                    height: 8,
                    decoration: BoxDecoration(
                      color: i == _page
                          ? scheme.primary
                          : scheme.onSurfaceVariant.withValues(alpha: 0.3),
                      borderRadius: BorderRadius.circular(999),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 24),
            Padding(
              padding: const EdgeInsets.fromLTRB(24, 0, 24, 20),
              child: SizedBox(
                height: 52,
                width: double.infinity,
                child: FilledButton(
                  onPressed: _next,
                  child: Text(isLast ? 'Get started' : 'Next',
                      style: const TextStyle(
                          fontSize: 15, fontWeight: FontWeight.w700)),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
