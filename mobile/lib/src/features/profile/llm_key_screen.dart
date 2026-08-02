import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/account_models.dart';
import 'llm_key_controller.dart';

/// The BYO providers the UI offers, in display order.
const _providers = <String, String>{
  'anthropic': 'Anthropic',
  'openai': 'OpenAI',
};

/// Profile → Your API key. Add/replace/remove a per-provider LLM key. A valid
/// key lifts the free-plan usage limits (processing runs on your own account).
class LlmKeyScreen extends ConsumerWidget {
  const LlmKeyScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final st = ref.watch(llmKeyControllerProvider);
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(title: const Text('Your API key')),
      body: st.loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 24),
              children: [
                Text(
                  'Add your own Anthropic or OpenAI key to run profile builds '
                  'and drafts on your own account — this removes the free-plan '
                  'monthly limits. Your key is stored encrypted and never shown '
                  'again after you save it.',
                  style: TextStyle(
                      fontSize: 13, height: 1.45, color: scheme.onSurfaceVariant),
                ),
                const SizedBox(height: 20),
                for (final entry in _providers.entries)
                  _ProviderCard(
                    provider: entry.key,
                    label: entry.value,
                    info: st.keys.forProvider(entry.key),
                    busy: st.busyProvider == entry.key,
                  ),
                if (st.error != null) ...[
                  const SizedBox(height: 12),
                  Text(st.error!, style: TextStyle(color: scheme.error)),
                ],
              ],
            ),
    );
  }
}

class _ProviderCard extends ConsumerWidget {
  const _ProviderCard({
    required this.provider,
    required this.label,
    required this.info,
    required this.busy,
  });

  final String provider;
  final String label;
  final LlmKeyInfo? info;
  final bool busy;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final scheme = Theme.of(context).colorScheme;
    final isSet = info != null;

    final (statusText, statusColor) = switch (info) {
      null => ('Not set', scheme.onSurfaceVariant),
      final k when k.valid => ('Set · validated', scheme.primary),
      final k when k.validated => ('Set · invalid key', scheme.error),
      _ => ('Set · validation pending', scheme.tertiary),
    };

    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(label,
                    style: const TextStyle(
                        fontSize: 16, fontWeight: FontWeight.w700)),
              ),
              if (busy)
                const SizedBox(
                    height: 16,
                    width: 16,
                    child: CircularProgressIndicator(strokeWidth: 2))
              else
                Text(statusText,
                    style: TextStyle(
                        fontSize: 12.5,
                        fontWeight: FontWeight.w600,
                        color: statusColor)),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: OutlinedButton(
                  onPressed: busy
                      ? null
                      : () => _enterKey(context, ref, provider, label),
                  child: Text(isSet ? 'Replace' : 'Add key'),
                ),
              ),
              if (isSet) ...[
                const SizedBox(width: 10),
                TextButton(
                  onPressed: busy
                      ? null
                      : () => ref
                          .read(llmKeyControllerProvider.notifier)
                          .remove(provider),
                  style: TextButton.styleFrom(foregroundColor: scheme.error),
                  child: const Text('Remove'),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }

  Future<void> _enterKey(
      BuildContext context, WidgetRef ref, String provider, String label) async {
    final key = await showDialog<String>(
      context: context,
      builder: (_) => _KeyEntryDialog(label: label),
    );
    if (key == null || key.isEmpty) return;
    final ok = await ref.read(llmKeyControllerProvider.notifier).save(provider, key);
    if (ok && context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('$label key saved')),
      );
    }
  }
}

class _KeyEntryDialog extends StatefulWidget {
  const _KeyEntryDialog({required this.label});
  final String label;

  @override
  State<_KeyEntryDialog> createState() => _KeyEntryDialogState();
}

class _KeyEntryDialogState extends State<_KeyEntryDialog> {
  final _ctrl = TextEditingController();
  bool _obscure = true;

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text('${widget.label} API key'),
      content: TextField(
        controller: _ctrl,
        obscureText: _obscure,
        autofocus: true,
        autocorrect: false,
        enableSuggestions: false,
        style: const TextStyle(fontFamily: 'RobotoMono'),
        decoration: InputDecoration(
          hintText: 'Paste your key',
          suffixIcon: IconButton(
            icon: Icon(_obscure
                ? Icons.visibility_outlined
                : Icons.visibility_off_outlined),
            onPressed: () => setState(() => _obscure = !_obscure),
          ),
        ),
        onSubmitted: (v) => Navigator.pop(context, v.trim()),
      ),
      actions: [
        TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel')),
        FilledButton(
            onPressed: () => Navigator.pop(context, _ctrl.text.trim()),
            child: const Text('Save')),
      ],
    );
  }
}
