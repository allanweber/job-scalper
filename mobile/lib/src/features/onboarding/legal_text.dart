import 'package:flutter/material.dart';

enum LegalKind { terms, privacy }

/// Opens a scrollable bottom sheet with the full legal prose. Reused by
/// onboarding consent and (later) Account → Settings.
Future<void> showLegalSheet(BuildContext context, LegalKind kind) {
  final doc = kind == LegalKind.terms ? _terms : _privacy;
  return showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (ctx) {
      final scheme = Theme.of(ctx).colorScheme;
      return DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.8,
        maxChildSize: 0.92,
        minChildSize: 0.5,
        builder: (_, controller) => ListView(
          controller: controller,
          padding: const EdgeInsets.fromLTRB(24, 0, 24, 32),
          children: [
            Text(doc.title,
                style: Theme.of(ctx)
                    .textTheme
                    .titleLarge
                    ?.copyWith(fontWeight: FontWeight.w800)),
            const SizedBox(height: 4),
            Text(doc.updated,
                style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
            const SizedBox(height: 16),
            Text(doc.body,
                style: TextStyle(
                    fontSize: 14, height: 1.55, color: scheme.onSurface)),
          ],
        ),
      );
    },
  );
}

class _LegalDoc {
  const _LegalDoc(this.title, this.updated, this.body);
  final String title;
  final String updated;
  final String body;
}

const _terms = _LegalDoc(
  'Terms of Service',
  'Last updated: July 2026',
  'Welcome to Job Scalper. By creating an account you agree to these terms.\n\n'
      '1. The service. Job Scalper aggregates publicly listed remote job postings '
      'and ranks them against the profile you provide. Match scores and generated '
      'application drafts are suggestions only — you are responsible for reviewing '
      'anything before you send it to an employer.\n\n'
      '2. Your account. You must provide accurate information and keep your '
      'credentials secure. One profile is included on the free plan, which scans '
      'up to three job boards.\n\n'
      '3. Acceptable use. Do not misuse the service, attempt to disrupt it, or use '
      'it to submit misleading applications. We may suspend accounts that abuse '
      'the platform.\n\n'
      '4. AI features. Drafts and insights are produced by AI models and may '
      'contain errors or "stretch" claims. Always verify factual statements about '
      'your experience before using a generated document.\n\n'
      '5. Availability. The service is provided "as is" without warranties. We may '
      'change or discontinue features at any time.\n\n'
      '6. Changes. We may update these terms; continued use after an update means '
      'you accept the revised terms.',
);

const _privacy = _LegalDoc(
  'Privacy Policy',
  'Last updated: July 2026',
  'This policy explains what Job Scalper collects and how it is used.\n\n'
      '1. What we collect. Your account details (name, email), the resume you '
      'upload, the profile you build from it, your selected job boards, saved '
      'postings, and generated drafts.\n\n'
      '2. How we use it. To rank job postings for you, to generate tailored '
      'application drafts, and to operate and improve the service. Your resume '
      'text is used to compute match scores and to ground generated documents.\n\n'
      '3. AI processing. Resume and profile text may be sent to AI model providers '
      'to build your profile and generate drafts. On the shared platform key, '
      'monthly limits apply; adding your own provider key keeps processing under '
      'your own account.\n\n'
      '4. Storage & control. Your data is stored to power the app across devices. '
      'You can edit your profile, replace your resume, or delete your account and '
      'all associated data at any time from Settings.\n\n'
      '5. Sharing. We do not sell your personal data. Job postings themselves come '
      'from public job boards.\n\n'
      '6. Contact. Reach us through the app if you have questions about your data.',
);
