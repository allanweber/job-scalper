import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/providers.dart';
import '../../state/session.dart';

/// The word the user must type to arm the destructive button.
const _confirmWord = 'DELETE';

/// Profile → Delete account. A dedicated, high-friction screen: it spells out
/// what is erased and requires typing DELETE before the button enables. On
/// success it signs out, which routes back to onboarding.
class DeleteAccountScreen extends ConsumerStatefulWidget {
  const DeleteAccountScreen({super.key});

  @override
  ConsumerState<DeleteAccountScreen> createState() =>
      _DeleteAccountScreenState();
}

class _DeleteAccountScreenState extends ConsumerState<DeleteAccountScreen> {
  final _ctrl = TextEditingController();
  bool _deleting = false;
  String? _error;

  bool get _armed => _ctrl.text.trim().toUpperCase() == _confirmWord;

  @override
  void initState() {
    super.initState();
    _ctrl.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  Future<void> _delete() async {
    setState(() {
      _deleting = true;
      _error = null;
    });
    try {
      await ref.read(accountRepositoryProvider).deleteAccount();
      // Signing out clears tokens; the router redirect sends us to onboarding.
      await ref.read(sessionProvider.notifier).signOut();
    } catch (e) {
      if (mounted) {
        setState(() {
          _deleting = false;
          _error = 'Could not delete your account. Check your connection and '
              'try again.';
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(title: const Text('Delete account')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 24),
        children: [
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: scheme.errorContainer,
              borderRadius: BorderRadius.circular(14),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(Icons.warning_amber_rounded, color: scheme.onErrorContainer),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    'This permanently deletes your account and cannot be undone.',
                    style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        color: scheme.onErrorContainer),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),
          Text('What gets erased',
              style:
                  const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          for (final item in const [
            'Your profile, resume and search settings',
            'Saved jobs and application drafts',
            'Any API keys you added',
            'Your job-board selection and usage history',
          ])
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 3),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.remove_rounded,
                      size: 18, color: scheme.onSurfaceVariant),
                  const SizedBox(width: 8),
                  Expanded(
                      child: Text(item, style: const TextStyle(fontSize: 14))),
                ],
              ),
            ),
          const SizedBox(height: 24),
          Text('Type $_confirmWord to confirm',
              style:
                  const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
          const SizedBox(height: 8),
          TextField(
            controller: _ctrl,
            autocorrect: false,
            enableSuggestions: false,
            textCapitalization: TextCapitalization.characters,
            decoration: const InputDecoration(
              hintText: _confirmWord,
              border: OutlineInputBorder(),
            ),
          ),
          if (_error != null) ...[
            const SizedBox(height: 12),
            Text(_error!, style: TextStyle(color: scheme.error)),
          ],
          const SizedBox(height: 20),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: scheme.error,
              foregroundColor: scheme.onError,
            ),
            onPressed: (!_armed || _deleting) ? null : _delete,
            child: _deleting
                ? const SizedBox(
                    height: 20,
                    width: 20,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Delete my account'),
          ),
        ],
      ),
    );
  }
}
