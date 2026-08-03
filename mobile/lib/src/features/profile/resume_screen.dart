import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../util/format.dart';
import 'resume_controller.dart';

/// Profile → Resume. Shows the stored resume, lets the user replace it, and
/// offers an opt-in "rebuild profile from resume".
class ResumeScreen extends ConsumerWidget {
  const ResumeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final st = ref.watch(resumeControllerProvider);
    final ctrl = ref.read(resumeControllerProvider.notifier);
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(title: const Text('Resume')),
      body: st.loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
              children: [
                if (st.hasResume)
                  _ResumeCard(
                    filename: st.resume!.filename ?? 'resume',
                    sizeBytes: st.resume!.sizeBytes,
                    updatedAt: st.resume!.updatedAt,
                  )
                else
                  _EmptyResume(scheme: scheme),
                const SizedBox(height: 16),
                OutlinedButton.icon(
                  onPressed: st.uploading ? null : () => _pickAndUpload(context, ref),
                  icon: st.uploading
                      ? const SizedBox(
                          height: 18,
                          width: 18,
                          child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.upload_file_rounded),
                  label: Text(st.hasResume ? 'Replace resume' : 'Upload resume'),
                ),
                if (st.error != null) ...[
                  const SizedBox(height: 12),
                  Text(st.error!, style: TextStyle(color: scheme.error)),
                ],
                if (st.hasResume) ...[
                  const SizedBox(height: 28),
                  Text('Rebuild your profile',
                      style: TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w700,
                          color: scheme.onSurface)),
                  const SizedBox(height: 6),
                  Text(
                    'Regenerate your search profile from this resume. This '
                    'replaces the titles, skills and keywords you currently have '
                    '— any manual edits will be overwritten.',
                    style: TextStyle(
                        fontSize: 13,
                        height: 1.45,
                        color: scheme.onSurfaceVariant),
                  ),
                  const SizedBox(height: 12),
                  _RebuildAction(st: st, onRebuild: ctrl.rebuildProfile),
                ],
              ],
            ),
    );
  }

  Future<void> _pickAndUpload(BuildContext context, WidgetRef ref) async {
    const group = XTypeGroup(
      label: 'Resume',
      extensions: ['pdf', 'doc', 'docx', 'txt', 'md'],
      mimeTypes: [
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'text/plain',
        'text/markdown',
      ],
    );
    try {
      final file = await openFile(acceptedTypeGroups: const [group]);
      if (file == null) return; // cancelled
      final bytes = await file.readAsBytes();
      await ref.read(resumeControllerProvider.notifier).replace(
            bytes: bytes,
            filename: file.name,
            contentType: file.mimeType,
          );
    } catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not read that file: $e')),
        );
      }
    }
  }
}

class _ResumeCard extends StatelessWidget {
  const _ResumeCard({
    required this.filename,
    required this.sizeBytes,
    required this.updatedAt,
  });

  final String filename;
  final int sizeBytes;
  final String updatedAt;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        children: [
          Icon(Icons.description_rounded, color: scheme.primary, size: 30),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(filename,
                    style: const TextStyle(
                        fontSize: 15, fontWeight: FontWeight.w700),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis),
                const SizedBox(height: 4),
                Text('${_kb(sizeBytes)} · updated ${relativeTime(updatedAt)}',
                    style: TextStyle(
                        fontSize: 12.5, color: scheme.onSurfaceVariant)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _kb(int bytes) {
    if (bytes <= 0) return '—';
    final kb = bytes / 1024;
    if (kb < 1024) return '${kb.toStringAsFixed(0)} KB';
    return '${(kb / 1024).toStringAsFixed(1)} MB';
  }
}

class _EmptyResume extends StatelessWidget {
  const _EmptyResume({required this.scheme});
  final ColorScheme scheme;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        children: [
          Icon(Icons.upload_file_outlined,
              color: scheme.onSurfaceVariant, size: 28),
          const SizedBox(width: 14),
          Expanded(
            child: Text(
              'No resume on file yet. Upload one to power better matches and '
              'application drafts.',
              style: TextStyle(fontSize: 13.5, color: scheme.onSurfaceVariant),
            ),
          ),
        ],
      ),
    );
  }
}

class _RebuildAction extends StatelessWidget {
  const _RebuildAction({required this.st, required this.onRebuild});

  final ResumeState st;
  final Future<void> Function() onRebuild;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    switch (st.rebuild) {
      case RebuildPhase.running:
        return const Row(
          children: [
            SizedBox(
                height: 18,
                width: 18,
                child: CircularProgressIndicator(strokeWidth: 2)),
            SizedBox(width: 12),
            Text('Rebuilding your profile…'),
          ],
        );
      case RebuildPhase.done:
        return Row(
          children: [
            Icon(Icons.check_circle_rounded, color: scheme.primary),
            const SizedBox(width: 8),
            const Expanded(
              child: Text('Profile rebuilt. Open Search profile to review it.'),
            ),
          ],
        );
      case RebuildPhase.failed:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(st.rebuildError ?? 'The rebuild failed.',
                style: TextStyle(color: scheme.error)),
            const SizedBox(height: 8),
            FilledButton.tonalIcon(
              onPressed: onRebuild,
              icon: const Icon(Icons.refresh_rounded),
              label: const Text('Try again'),
            ),
          ],
        );
      case RebuildPhase.idle:
        return FilledButton.tonalIcon(
          onPressed: onRebuild,
          icon: const Icon(Icons.auto_awesome_rounded),
          label: const Text('Rebuild profile from resume'),
        );
    }
  }
}
