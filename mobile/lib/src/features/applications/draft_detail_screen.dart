import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../data/models/draft_models.dart';
import '../../data/providers.dart';
import '../../theme/tokens.dart';
import '../../util/format.dart';
import 'application_status.dart';
import 'draft_detail_controller.dart';
import 'draft_pdf.dart';
import 'pdf_saver_stub.dart'
    if (dart.library.io) 'pdf_saver_io.dart';

Future<void> _openUrl(String url) async {
  final uri = Uri.tryParse(url);
  if (uri != null) {
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }
}

/// Download a PDF using a 3-step priority:
///   1. Local sqflite cache (instant, no network)
///   2. API → pdf-service (server-rendered, saved to cache)
///   3. On-device fallback via the `pdf` package (offline / service down)
Future<void> _downloadPdf(
  BuildContext context,
  WidgetRef ref, {
  required String draftId,
  required String docType, // "resume" | "cover_letter"
  required String title,
  required String filename,
  String? markdown,
}) async {
  final messenger = ScaffoldMessenger.of(context);
  final cache = ref.read(pdfCacheRepositoryProvider);
  final repo = ref.read(draftsRepositoryProvider);

  Future<void> openBytes(Uint8List bytes) async {
    await savePdfToDevice(filename, bytes);
  }

  // 1. Cache hit
  final cached = await cache.get(draftId, docType);
  if (cached != null) {
    await openBytes(cached);
    return;
  }

  // 2. API → pdf-service
  try {
    final bytes = await repo.getDraftPdf(draftId, docType);
    await cache.put(draftId, docType, bytes);
    await openBytes(bytes);
    return;
  } catch (_) {
    // fall through to on-device generation
  }

  // 3. On-device fallback
  if (!context.mounted) return;
  final md = markdown?.trim() ?? '';
  if (md.isEmpty) {
    messenger.showSnackBar(
        const SnackBar(content: Text('Nothing to export yet')));
    return;
  }
  try {
    final bytes = await buildDraftPdf(title: title, markdown: md);
    await openBytes(bytes);
    if (!context.mounted) return;
    messenger.showSnackBar(const SnackBar(
        content: Text('Generated locally — PDF service unavailable')));
  } catch (e) {
    if (!context.mounted) return;
    messenger.showSnackBar(SnackBar(content: Text("Couldn't save PDF ($e)")));
  }
}

/// One generated application: switch between the tailored resume and cover
/// letter, read them, and edit either in place. [initial] (passed via the route
/// `extra`) lets the header render instantly while the full draft loads.
class DraftDetailScreen extends ConsumerStatefulWidget {
  const DraftDetailScreen({super.key, required this.draftId, this.initial});

  final String draftId;
  final DraftSummary? initial;

  @override
  ConsumerState<DraftDetailScreen> createState() => _DraftDetailScreenState();
}

class _DraftDetailScreenState extends ConsumerState<DraftDetailScreen> {
  DraftDoc _doc = DraftDoc.resume;

  @override
  void initState() {
    super.initState();
    Future.microtask(
        () => ref.read(draftDetailControllerProvider.notifier).load(widget.draftId));
  }

  String get _title => widget.initial?.displayTitle ?? 'Application';

  String? _content(Draft d) =>
      _doc == DraftDoc.resume ? d.resumeMd : d.coverLetterMd;

  Future<void> _edit(Draft d) async {
    final current = _content(d) ?? '';
    final label = _doc == DraftDoc.resume ? 'Resume' : 'Cover letter';
    final edited = await Navigator.of(context).push<String>(
      MaterialPageRoute(
        fullscreenDialog: true,
        builder: (_) => _DraftEditorPage(title: 'Edit $label', initial: current),
      ),
    );
    if (edited == null || edited == current) return;
    final ctrl = ref.read(draftDetailControllerProvider.notifier);
    final ok = await ctrl.saveDoc(_doc, edited);
    if (!mounted) return;
    final err = ref.read(draftDetailControllerProvider).saveError;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(ok ? '$label saved' : (err ?? "Couldn't save"))));
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(draftDetailControllerProvider);
    final ctrl = ref.read(draftDetailControllerProvider.notifier);
    final d = state.draft;

    return Scaffold(
      appBar: AppBar(
        title: Text(_title, maxLines: 1, overflow: TextOverflow.ellipsis),
        actions: [
          // Regenerate + edit are only available once the content is in (ready).
          if (state.status == DraftDetailStatus.ready &&
              d != null &&
              d.isReady) ...[
            IconButton(
              tooltip: 'Regenerate',
              onPressed: state.regenerating ? null : () => _regenerate(d),
              icon: state.regenerating
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.autorenew_rounded),
            ),
            IconButton(
              tooltip: 'Edit',
              onPressed: state.saving ? null : () => _edit(d),
              icon: const Icon(Icons.edit_outlined),
            ),
          ],
        ],
      ),
      body: switch (state.status) {
        DraftDetailStatus.loading =>
          const Center(child: CircularProgressIndicator()),
        DraftDetailStatus.error => _ErrorView(
            message: state.error ?? 'Something went wrong.',
            onRetry: ctrl.refresh),
        DraftDetailStatus.ready when d!.isPending => const _Drafting(),
        DraftDetailStatus.ready when d!.isFailed => _DraftFailed(
            error: d.error,
            postingId: d.postingId,
            draftId: d.id,
          ),
        DraftDetailStatus.ready => _Ready(
            draft: d!,
            summary: widget.initial,
            doc: _doc,
            onDocChanged: (v) => setState(() => _doc = v),
            content: _content(d),
            applying: state.applying,
            // Fall back to 'applied' for a draft flagged applied without an
            // explicit stage (e.g. pre-pipeline data), so it still reads as
            // in the pipeline.
            status: d.applicationStatus ?? (d.applied ? 'applied' : null),
            onSetStatus: (s) => _setStatus(s),
          ),
      },
    );
  }

  Future<void> _regenerate(Draft d) async {
    final tone = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (_) => _TonePicker(current: d.tone ?? 'professional'),
    );
    if (tone == null || !mounted) return; // dismissed
    final ok = await ref
        .read(draftDetailControllerProvider.notifier)
        .regenerate(tone: tone);
    if (!mounted) return;
    if (ok) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text('Regenerating in a ${kDraftToneLabels[tone]} tone…')));
    } else {
      final err = ref.read(draftDetailControllerProvider).saveError;
      ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(err ?? "Couldn't regenerate — try again.")));
    }
  }

  Future<void> _setStatus(String? status) async {
    final ok = await ref
        .read(draftDetailControllerProvider.notifier)
        .setApplicationStatus(status);
    if (!mounted) return;
    final message = ok
        ? (status == null
            ? 'Removed from your applications'
            : 'Updated to ${applicationStageLabel(status)}')
        : "Couldn't update — try again.";
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(message)));
  }
}

class _Ready extends StatelessWidget {
  const _Ready({
    required this.draft,
    required this.summary,
    required this.doc,
    required this.onDocChanged,
    required this.content,
    required this.applying,
    required this.status,
    required this.onSetStatus,
  });

  final Draft draft;
  final DraftSummary? summary;
  final DraftDoc doc;
  final ValueChanged<DraftDoc> onDocChanged;
  final String? content;
  final bool applying;
  final String? status;
  final ValueChanged<String?> onSetStatus;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final company = summary?.company;
    final when = relativeTime(draft.createdAt);
    final url = summary?.url;
    final pdfTitle = summary?.displayTitle ?? 'Application';

    return ListView(
      padding: const EdgeInsets.fromLTRB(AppTokens.screenPadding, 12,
          AppTokens.screenPadding, 32),
      children: [
        if (company != null && company.isNotEmpty)
          Text(company,
              style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  color: scheme.onSurfaceVariant)),
        if (when != null) ...[
          const SizedBox(height: 4),
          Text('Drafted $when',
              style: TextStyle(fontSize: 12.5, color: scheme.onSurfaceVariant)),
        ],
        if (url != null && url.isNotEmpty || draft.postingId != null) ...[
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              if (url != null && url.isNotEmpty)
                FilledButton.tonalIcon(
                  onPressed: () => _openUrl(url),
                  icon: const Icon(Icons.open_in_new_rounded, size: 18),
                  label: const Text('View job posting'),
                ),
              if (draft.postingId != null)
                OutlinedButton.icon(
                  // Absolute path into this draft's nested job route — go_router
                  // treats push() strings as absolute, so a bare 'job/…' would
                  // resolve to /job/… and match no route.
                  onPressed: () => context.push(
                      '/applications/draft/${draft.id}/job/${draft.postingId}'),
                  icon: const Icon(Icons.analytics_outlined, size: 18),
                  label: const Text('Job analysis'),
                ),
            ],
          ),
        ],
        if (draft.matchedSkills.isNotEmpty) ...[
          const SizedBox(height: 14),
          _WhyThisDraft(skills: draft.matchedSkills, tone: draft.tone),
        ],
        const SizedBox(height: 12),
        _ApplicationStatusControl(
            status: status, busy: applying, onSetStatus: onSetStatus),
        const SizedBox(height: 12),
        _PdfButtons(draft: draft, pdfTitle: pdfTitle),
        const SizedBox(height: 14),
        SegmentedButton<DraftDoc>(
          segments: const [
            ButtonSegment(
                value: DraftDoc.resume,
                icon: Icon(Icons.article_outlined),
                label: Text('Resume')),
            ButtonSegment(
                value: DraftDoc.coverLetter,
                icon: Icon(Icons.mail_outline_rounded),
                label: Text('Cover letter')),
          ],
          selected: {doc},
          onSelectionChanged: (s) => onDocChanged(s.first),
        ),
        if (doc == DraftDoc.resume &&
            (draft.stretchClaimsMd?.trim().isNotEmpty ?? false)) ...[
          const SizedBox(height: 14),
          _StretchClaims(text: draft.stretchClaimsMd!),
        ],
        const SizedBox(height: 16),
        _Document(text: content),
      ],
    );
  }
}

/// Cover-letter/summary voices offered for (re)generation. Mirrors the backend
/// DRAFT_TONES; 'professional' is the default.
const kDraftTones = ['professional', 'warm', 'confident', 'concise'];
const kDraftToneLabels = {
  'professional': 'Professional',
  'warm': 'Warm',
  'confident': 'Confident',
  'concise': 'Concise',
};
const _kDraftToneBlurbs = {
  'professional': 'Polished and neutral (default)',
  'warm': 'Friendly and personable',
  'confident': 'Assertive, results-forward',
  'concise': 'Short and punchy',
};

/// "Why this draft": the profile skills this posting matched, so the user can
/// see what the tailoring leaned on (and the tone it was written in).
class _WhyThisDraft extends StatelessWidget {
  const _WhyThisDraft({required this.skills, required this.tone});
  final List<String> skills;
  final String? tone;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.auto_awesome_rounded,
                  size: 16, color: scheme.primary),
              const SizedBox(width: 8),
              Expanded(
                child: Text('Why this draft',
                    style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: scheme.onSurface)),
              ),
              if (tone != null && tone != 'professional')
                Text('${kDraftToneLabels[tone] ?? tone} tone',
                    style: TextStyle(
                        fontSize: 12, color: scheme.onSurfaceVariant)),
            ],
          ),
          const SizedBox(height: 6),
          Text('Tailored around the skills this role asks for that are in your '
              'profile:',
              style: TextStyle(fontSize: 12.5, color: scheme.onSurfaceVariant)),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final s in skills)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                  decoration: BoxDecoration(
                    color: scheme.primaryContainer,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(s,
                      style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                          color: scheme.onPrimaryContainer)),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

/// Bottom sheet to pick a tone for regeneration; pops the chosen tone slug.
class _TonePicker extends StatelessWidget {
  const _TonePicker({required this.current});
  final String current;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 4, 20, 4),
            child: Text('Regenerate in a tone',
                style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w800,
                    color: scheme.onSurface)),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 0, 20, 12),
            child: Text('Uses one draft credit to rewrite this application.',
                style: TextStyle(fontSize: 12.5, color: scheme.onSurfaceVariant)),
          ),
          for (final t in kDraftTones)
            ListTile(
              title: Text(kDraftToneLabels[t]!),
              subtitle: Text(_kDraftToneBlurbs[t]!),
              trailing: t == current
                  ? Icon(Icons.check_rounded, color: scheme.primary)
                  : null,
              onTap: () => Navigator.of(context).pop(t),
            ),
          const SizedBox(height: 8),
        ],
      ),
    );
  }
}

/// The application-tracking control. Before applying it's a single prominent
/// call to action; once in the pipeline it becomes a stage picker (Applied →
/// Interviewing → Offer, with Rejected as an off-ramp) plus a way to remove the
/// job from the pipeline entirely.
class _ApplicationStatusControl extends StatelessWidget {
  const _ApplicationStatusControl({
    required this.status,
    required this.busy,
    required this.onSetStatus,
  });
  final String? status;
  final bool busy;
  final ValueChanged<String?> onSetStatus;

  @override
  Widget build(BuildContext context) {
    if (status == null) {
      return SizedBox(
        width: double.infinity,
        child: FilledButton.icon(
          onPressed: busy ? null : () => onSetStatus('applied'),
          icon: busy
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.check_circle_outline_rounded, size: 20),
          label: const Text('Mark as applied'),
        ),
      );
    }

    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text('Application status',
                    style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: scheme.onSurface)),
              ),
              if (busy)
                const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2))
              else
                TextButton(
                  onPressed: () => onSetStatus(null),
                  style: TextButton.styleFrom(
                      padding: const EdgeInsets.symmetric(horizontal: 8),
                      minimumSize: const Size(0, 32),
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap),
                  child: const Text('Remove'),
                ),
            ],
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final stage in kApplicationStages)
                _StageChip(
                  stage: stage,
                  selected: stage == status,
                  onSelected: busy ? null : () => onSetStatus(stage),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

/// One selectable pipeline stage. Selected chips take the stage's color; the
/// rest are quiet outlines so the current stage reads at a glance.
class _StageChip extends StatelessWidget {
  const _StageChip({
    required this.stage,
    required this.selected,
    required this.onSelected,
  });
  final String stage;
  final bool selected;
  final VoidCallback? onSelected;

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final scheme = Theme.of(context).colorScheme;
    final colors = applicationStageColors(stage, dark);
    return Material(
      color: selected ? colors.bg : Colors.transparent,
      shape: StadiumBorder(
        side: BorderSide(
            color: selected ? colors.bg : scheme.outlineVariant),
      ),
      child: InkWell(
        customBorder: const StadiumBorder(),
        onTap: onSelected,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
          child: Text(
            applicationStageLabel(stage),
            style: TextStyle(
              fontSize: 12.5,
              fontWeight: FontWeight.w700,
              color: selected ? colors.fg : scheme.onSurfaceVariant,
            ),
          ),
        ),
      ),
    );
  }
}

class _PdfButtons extends ConsumerWidget {
  const _PdfButtons({required this.draft, required this.pdfTitle});

  final Draft draft;
  final String pdfTitle;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        FilledButton.tonalIcon(
          onPressed: () => _downloadPdf(context, ref,
              draftId: draft.id,
              docType: 'resume',
              title: '$pdfTitle — Resume',
              filename: 'resume.pdf',
              markdown: draft.resumeMd),
          icon: const Icon(Icons.download_rounded, size: 18),
          label: const Text('Resume PDF'),
        ),
        const SizedBox(height: 8),
        FilledButton.tonalIcon(
          onPressed: () => _downloadPdf(context, ref,
              draftId: draft.id,
              docType: 'cover_letter',
              title: '$pdfTitle — Cover letter',
              filename: 'cover_letter.pdf',
              markdown: draft.coverLetterMd),
          icon: const Icon(Icons.download_rounded, size: 18),
          label: const Text('Cover letter PDF'),
        ),
      ],
    );
  }
}

/// Renders a document's markdown as readable, selectable text. (The content is
/// light markdown; we present it verbatim so what you read is what you edit.)
class _Document extends StatelessWidget {
  const _Document({required this.text});
  final String? text;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final t = text;
    if (t == null || t.trim().isEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 24),
        child: Text('This document is empty. Tap edit to write it.',
            style: TextStyle(color: scheme.onSurfaceVariant)),
      );
    }
    return SelectableText(
      t,
      style: TextStyle(
          fontSize: 14.5, height: 1.5, color: scheme.onSurface),
    );
  }
}

class _StretchClaims extends StatelessWidget {
  const _StretchClaims({required this.text});
  final String text;

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: dark ? AppTokens.chipTanBgDark : AppTokens.chipTanBgLight,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.flag_outlined,
              size: 18,
              color: dark
                  ? AppTokens.chipTanTextDark
                  : AppTokens.chipTanTextLight),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Claims to double-check',
                    style: TextStyle(
                        fontSize: 12.5,
                        fontWeight: FontWeight.w700,
                        color: dark
                            ? AppTokens.chipTanTextDark
                            : AppTokens.chipTanTextLight)),
                const SizedBox(height: 4),
                Text(text,
                    style: TextStyle(
                        fontSize: 12.5,
                        height: 1.4,
                        color: dark
                            ? AppTokens.chipTanTextDark
                            : AppTokens.chipTanTextLight)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Full-screen editor for one document; pops the edited markdown on save.
class _DraftEditorPage extends StatefulWidget {
  const _DraftEditorPage({required this.title, required this.initial});
  final String title;
  final String initial;

  @override
  State<_DraftEditorPage> createState() => _DraftEditorPageState();
}

class _DraftEditorPageState extends State<_DraftEditorPage> {
  late final TextEditingController _c = TextEditingController(text: widget.initial);

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(widget.title)),
      body: Padding(
        padding: const EdgeInsets.all(AppTokens.screenPadding),
        child: TextField(
          controller: _c,
          maxLines: null,
          expands: true,
          textAlignVertical: TextAlignVertical.top,
          keyboardType: TextInputType.multiline,
          style: const TextStyle(fontSize: 14.5, height: 1.5),
          decoration: const InputDecoration(
            border: InputBorder.none,
            hintText: 'Write in Markdown…',
          ),
        ),
      ),
      bottomNavigationBar: SafeArea(
        minimum: const EdgeInsets.fromLTRB(AppTokens.screenPadding, 8,
            AppTokens.screenPadding, 12),
        child: SizedBox(
          width: double.infinity,
          child: FilledButton.icon(
            onPressed: () => Navigator.of(context).pop(_c.text),
            icon: const Icon(Icons.check_rounded),
            label: const Text('Save changes'),
          ),
        ),
      ),
    );
  }
}

/// Shown while the worker is still generating the draft. All the actions live
/// on [_Ready], so simply rendering this keeps them disabled until it's done.
class _Drafting extends StatelessWidget {
  const _Drafting();

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(
                width: 34,
                height: 34,
                child: CircularProgressIndicator(strokeWidth: 3)),
            const SizedBox(height: 20),
            Text('Drafting your application…',
                style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: scheme.onSurface)),
            const SizedBox(height: 8),
            Text(
              'Tailoring your resume and cover letter to this role. This usually '
              'takes a few seconds — you can leave this page and it will be '
              'waiting in your Applications.',
              textAlign: TextAlign.center,
              style: TextStyle(
                  fontSize: 13, height: 1.45, color: scheme.onSurfaceVariant),
            ),
          ],
        ),
      ),
    );
  }
}

/// Shown when drafting failed, with the reason and a way back to the job.
class _DraftFailed extends StatelessWidget {
  const _DraftFailed({
    required this.error,
    required this.postingId,
    required this.draftId,
  });

  final String? error;
  final String? postingId;
  final String draftId;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.error_outline_rounded, size: 48, color: scheme.error),
            const SizedBox(height: 16),
            Text("Couldn't finish this draft",
                style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: scheme.onSurface)),
            const SizedBox(height: 8),
            Text(
              error?.trim().isNotEmpty == true
                  ? error!
                  : 'Something went wrong while drafting. Please try again.',
              textAlign: TextAlign.center,
              style: TextStyle(
                  fontSize: 13, height: 1.45, color: scheme.onSurfaceVariant),
            ),
            if (postingId != null) ...[
              const SizedBox(height: 20),
              OutlinedButton.icon(
                onPressed: () => context.push(
                    '/applications/draft/$draftId/job/$postingId'),
                icon: const Icon(Icons.analytics_outlined, size: 18),
                label: const Text('View the job'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.message, required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.cloud_off_rounded,
                size: 48, color: scheme.onSurfaceVariant),
            const SizedBox(height: 16),
            Text("Couldn't load this draft",
                style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: scheme.onSurface)),
            const SizedBox(height: 8),
            Text(message,
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 13, color: scheme.onSurfaceVariant)),
            const SizedBox(height: 20),
            FilledButton.tonal(onPressed: onRetry, child: const Text('Retry')),
          ],
        ),
      ),
    );
  }
}
