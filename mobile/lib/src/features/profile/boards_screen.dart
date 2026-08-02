import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../onboarding/board_catalog.dart';
import 'boards_controller.dart';

/// Profile → Job boards. Choose which boards we scan, capped at the plan limit.
class BoardsScreen extends ConsumerWidget {
  const BoardsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final st = ref.watch(boardsControllerProvider);
    final ctrl = ref.read(boardsControllerProvider.notifier);
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(title: const Text('Job boards')),
      body: st.loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
              children: [
                Text(
                  'Pick up to ${st.maxAllowed} boards to scan '
                  '(${st.selected.length}/${st.maxAllowed} selected).',
                  style: TextStyle(
                      fontSize: 13, color: scheme.onSurfaceVariant, height: 1.4),
                ),
                const SizedBox(height: 12),
                for (final slug in st.available)
                  _BoardRow(
                    slug: slug,
                    selected: st.selected.contains(slug),
                    enabled: st.selected.contains(slug) || !st.atLimit,
                    onChanged: () {
                      final ok = ctrl.toggle(slug);
                      if (!ok) {
                        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                          content: Text(
                              'That\'s the maximum of ${st.maxAllowed} boards. '
                              'Remove one first.'),
                        ));
                      }
                    },
                  ),
                if (st.error != null) ...[
                  const SizedBox(height: 12),
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
                        final ok = await ctrl.save();
                        if (ok && context.mounted) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(content: Text('Boards updated')),
                          );
                        }
                      },
                child: st.saving
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('Save'),
              ),
            ),
    );
  }
}

class _BoardRow extends StatelessWidget {
  const _BoardRow({
    required this.slug,
    required this.selected,
    required this.enabled,
    required this.onChanged,
  });

  final String slug;
  final bool selected;
  final bool enabled;
  final VoidCallback onChanged;

  @override
  Widget build(BuildContext context) {
    final info = boardInfo(slug);
    final scheme = Theme.of(context).colorScheme;
    return Opacity(
      opacity: enabled ? 1 : 0.5,
      child: CheckboxListTile(
        contentPadding: EdgeInsets.zero,
        value: selected,
        onChanged: enabled ? (_) => onChanged() : null,
        title: Text(info.name,
            style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
        subtitle: Text(info.blurb,
            style: TextStyle(fontSize: 12.5, color: scheme.onSurfaceVariant)),
      ),
    );
  }
}
