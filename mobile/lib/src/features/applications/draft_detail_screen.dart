import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../data/models/draft_models.dart';
import '../../data/providers.dart';
import '../../theme/tokens.dart';
import '../../util/format.dart';
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
          if (state.status == DraftDetailStatus.ready && d != null)
            IconButton(
              tooltip: 'Edit',
              onPressed: state.saving ? null : () => _edit(d),
              icon: const Icon(Icons.edit_outlined),
            ),
        ],
      ),
      body: switch (state.status) {
        DraftDetailStatus.loading =>
          const Center(child: CircularProgressIndicator()),
        DraftDetailStatus.error => _ErrorView(
            message: state.error ?? 'Something went wrong.',
            onRetry: ctrl.refresh),
        DraftDetailStatus.ready => _Ready(
            draft: d!,
            summary: widget.initial,
            doc: _doc,
            onDocChanged: (v) => setState(() => _doc = v),
            content: _content(d),
          ),
      },
    );
  }
}

class _Ready extends StatelessWidget {
  const _Ready({
    required this.draft,
    required this.summary,
    required this.doc,
    required this.onDocChanged,
    required this.content,
  });

  final Draft draft;
  final DraftSummary? summary;
  final DraftDoc doc;
  final ValueChanged<DraftDoc> onDocChanged;
  final String? content;

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
        if (url != null && url.isNotEmpty) ...[
          const SizedBox(height: 12),
          Align(
            alignment: Alignment.centerLeft,
            child: FilledButton.tonalIcon(
              onPressed: () => _openUrl(url),
              icon: const Icon(Icons.open_in_new_rounded, size: 18),
              label: const Text('View job posting'),
            ),
          ),
        ],
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
