import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'profile_edit_controller.dart';
import 'widgets/profile_form_fields.dart';

/// Profile → Search profile. Edits the match profile with the shared form and
/// saves it with `PUT /me/profile`.
class ProfileEditScreen extends ConsumerWidget {
  const ProfileEditScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final st = ref.watch(profileEditControllerProvider);
    final ctrl = ref.read(profileEditControllerProvider.notifier);
    final scheme = Theme.of(context).colorScheme;

    return PopScope(
      canPop: !st.dirty,
      onPopInvokedWithResult: (didPop, _) async {
        if (didPop) return;
        final discard = await _confirmDiscard(context);
        if (discard == true && context.mounted) Navigator.of(context).pop();
      },
      child: Scaffold(
        appBar: AppBar(title: const Text('Search profile')),
        body: st.loading
            ? const Center(child: CircularProgressIndicator())
            : ListView(
                padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
                children: [
                  Text(
                    'This is what we rank job postings against. Changes take '
                    'effect on your next feed refresh.',
                    style: TextStyle(
                        fontSize: 13, color: scheme.onSurfaceVariant, height: 1.4),
                  ),
                  const SizedBox(height: 20),
                  ProfileFormFields(
                    value: st.working,
                    onChanged: ctrl.update,
                  ),
                  if (st.error != null) ...[
                    const SizedBox(height: 16),
                    Text(st.error!, style: TextStyle(color: scheme.error)),
                  ],
                ],
              ),
        bottomNavigationBar: st.loading
            ? null
            : SafeArea(
                minimum: const EdgeInsets.fromLTRB(20, 8, 20, 12),
                child: FilledButton(
                  onPressed: (!st.dirty || st.saving)
                      ? null
                      : () async {
                          FocusScope.of(context).unfocus();
                          final ok = await ctrl.save();
                          if (ok && context.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(content: Text('Profile saved')),
                            );
                          }
                        },
                  child: st.saving
                      ? const SizedBox(
                          height: 20,
                          width: 20,
                          child: CircularProgressIndicator(strokeWidth: 2))
                      : const Text('Save changes'),
                ),
              ),
      ),
    );
  }

  Future<bool?> _confirmDiscard(BuildContext context) => showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Discard changes?'),
          content: const Text('You have unsaved edits to your search profile.'),
          actions: [
            TextButton(
                onPressed: () => Navigator.pop(ctx, false),
                child: const Text('Keep editing')),
            FilledButton(
                onPressed: () => Navigator.pop(ctx, true),
                child: const Text('Discard')),
          ],
        ),
      );
}
