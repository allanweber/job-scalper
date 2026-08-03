import 'dart:typed_data';

import 'package:file_selector/file_selector.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../onboarding_controller.dart';
import '../widgets/onboarding_scaffold.dart';

/// Step 5 — upload resume. Pick a PDF/DOC(X)/TXT, show a selected-file card,
/// then "Build my profile" uploads the bytes (`PUT /me/resume`) and kicks
/// off the async profile build. Uses `file_selector` (the official federated
/// plugin) so the native Android/iOS builds stay compatible with current Flutter.
class ResumeStep extends ConsumerStatefulWidget {
  const ResumeStep({super.key});

  @override
  ConsumerState<ResumeStep> createState() => _ResumeStepState();
}

class _ResumeStepState extends ConsumerState<ResumeStep> {
  Uint8List? _bytes;
  String? _name;
  String? _pickError;

  Future<void> _pick() async {
    setState(() => _pickError = null);
    try {
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
      final file = await openFile(acceptedTypeGroups: const [group]);
      if (file == null) return; // cancelled
      final bytes = await file.readAsBytes();
      setState(() {
        _bytes = bytes;
        _name = file.name;
      });
    } catch (e) {
      setState(() => _pickError = 'File picker error: $e');
    }
  }

  Future<void> _submit() async {
    final bytes = _bytes;
    final name = _name;
    if (bytes == null || name == null) return;
    await ref.read(onboardingControllerProvider.notifier).submitResume(
          bytes: bytes,
          filename: name,
          contentType: _contentType(name),
        );
  }

  String? _contentType(String name) {
    final ext = name.contains('.') ? name.split('.').last.toLowerCase() : '';
    return switch (ext) {
      'pdf' => 'application/pdf',
      'doc' => 'application/msword',
      'docx' =>
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'txt' => 'text/plain',
      'md' => 'text/markdown',
      _ => null,
    };
  }

  @override
  Widget build(BuildContext context) {
    final st = ref.watch(onboardingControllerProvider);
    final ctrl = ref.read(onboardingControllerProvider.notifier);
    final hasFile = _bytes != null;
    return OnboardingScaffold(
      progress: 5 / 8,
      title: 'Add your resume',
      subtitle:
          'We read it once to build your match profile and to ground the drafts we '
          'generate. PDF, Word, or text.',
      onBack: ctrl.back,
      busy: st.busy,
      error: _pickError ?? st.error,
      primaryLabel: 'Build my profile',
      primaryEnabled: hasFile,
      onPrimary: _submit,
      child: hasFile
          ? _FileCard(
              name: _name!,
              size: _bytes!.length,
              onClear: () => setState(() {
                _bytes = null;
                _name = null;
              }),
            )
          : _Dropzone(onTap: _pick),
    );
  }
}

class _Dropzone extends StatelessWidget {
  const _Dropzone({required this.onTap});
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Container(
        height: 180,
        decoration: BoxDecoration(
          color: scheme.surfaceContainerLow,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: scheme.outlineVariant),
        ),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.upload_file_rounded, size: 44, color: scheme.primary),
            const SizedBox(height: 14),
            Text('Choose a file',
                style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w700,
                    color: scheme.onSurface)),
            const SizedBox(height: 4),
            Text('PDF, DOC, DOCX, TXT',
                style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
          ],
        ),
      ),
    );
  }
}

class _FileCard extends StatelessWidget {
  const _FileCard({
    required this.name,
    required this.size,
    required this.onClear,
  });

  final String name;
  final int size;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: scheme.primary.withValues(alpha: 0.5)),
      ),
      child: Row(
        children: [
          Container(
            width: 44,
            height: 44,
            decoration: BoxDecoration(
              color: scheme.primaryContainer,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(Icons.description_rounded,
                color: scheme.onPrimaryContainer),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 14, fontWeight: FontWeight.w600)),
                const SizedBox(height: 2),
                Text(_fmtSize(size),
                    style: TextStyle(
                        fontSize: 12, color: scheme.onSurfaceVariant)),
              ],
            ),
          ),
          IconButton(
            onPressed: onClear,
            icon: const Icon(Icons.close),
            tooltip: 'Remove',
          ),
        ],
      ),
    );
  }

  String _fmtSize(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(0)} KB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }
}
