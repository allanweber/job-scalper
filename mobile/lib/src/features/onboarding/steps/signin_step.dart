import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../config/env.dart';
import '../../../theme/tokens.dart';
import '../onboarding_controller.dart';

/// Step 2 — sign in. A single "Continue with Google" button; on device this is
/// the native Google flow, on the web verification build it posts the dev
/// id-token stand-in. The app's own JWT pair comes back from `POST /auth/google`.
class SignInStep extends ConsumerWidget {
  const SignInStep({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    final st = ref.watch(onboardingControllerProvider);
    final ctrl = ref.read(onboardingControllerProvider.notifier);

    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Align(
                alignment: Alignment.centerLeft,
                child: IconButton(
                  onPressed: st.busy ? null : ctrl.back,
                  icon: const Icon(Icons.arrow_back),
                ),
              ),
              const Spacer(),
              Center(
                child: Image.asset('assets/brand/icon-circle.png',
                    width: 88, height: 88),
              ),
              const SizedBox(height: 28),
              Text('Sign in to continue',
                  textAlign: TextAlign.center,
                  style: Theme.of(context)
                      .textTheme
                      .headlineSmall
                      ?.copyWith(fontWeight: FontWeight.w800)),
              const SizedBox(height: 10),
              Text(
                'Your profile, saved jobs, and drafts sync to your account.',
                textAlign: TextAlign.center,
                style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 14),
              ),
              const Spacer(),
              if (st.error != null) ...[
                Text(st.error!,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                        color: AppTokens.destructive, fontSize: 13)),
                const SizedBox(height: 12),
              ],
              _GoogleButton(
                busy: st.busy,
                onPressed: st.busy ? null : () => ctrl.signIn(Env.devIdToken),
              ),
              const SizedBox(height: 16),
              Text(
                'By continuing you agree to our Terms and Privacy Policy.',
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

class _GoogleButton extends StatelessWidget {
  const _GoogleButton({required this.busy, required this.onPressed});
  final bool busy;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return SizedBox(
      height: 52,
      child: OutlinedButton(
        onPressed: onPressed,
        style: OutlinedButton.styleFrom(
          side: BorderSide(color: scheme.outlineVariant),
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        ),
        child: busy
            ? const SizedBox(
                width: 22,
                height: 22,
                child: CircularProgressIndicator(strokeWidth: 2.2))
            : Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const _GoogleMark(),
                  const SizedBox(width: 12),
                  Text('Continue with Google',
                      style: TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                          color: scheme.onSurface)),
                ],
              ),
      ),
    );
  }
}

/// The 4-color Google "G" mark (mock swatch — replace with the branded platform
/// Google Sign-In button in production).
class _GoogleMark extends StatelessWidget {
  const _GoogleMark();

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 20,
      height: 20,
      child: CustomPaint(painter: _GPainter()),
    );
  }
}

class _GPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final c = size.center(Offset.zero);
    final r = size.width / 2;
    final rect = Rect.fromCircle(center: c, radius: r);
    final stroke = size.width * 0.28;
    final colors = [
      const Color(0xFFEA4335), // red   top-left
      const Color(0xFFFBBC05), // yellow bottom-left
      const Color(0xFF34A853), // green bottom-right
      const Color(0xFF4285F4), // blue  top-right
    ];
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke;
    // Four quadrant arcs.
    for (var i = 0; i < 4; i++) {
      paint.color = colors[i];
      canvas.drawArc(rect.deflate(stroke / 2), (2 + i) * 1.5708, 1.5708, false, paint);
    }
    // The blue crossbar of the "G" (center to the right edge of the ring).
    final bar = Paint()..color = colors[3];
    canvas.drawRect(Rect.fromLTWH(c.dx, c.dy - stroke / 2, r, stroke), bar);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
