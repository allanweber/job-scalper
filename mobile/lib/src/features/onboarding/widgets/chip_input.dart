import 'package:flutter/material.dart';

/// A labeled chip-input group: type text, press Enter or tap Add to append a
/// chip; tap a chip's ✕ to remove it. Used in the onboarding profile review and
/// (later) the Account → Match profile editor.
class ChipInput extends StatefulWidget {
  const ChipInput({
    super.key,
    required this.label,
    required this.values,
    required this.onChanged,
    this.hint,
    this.chipColor,
    this.chipTextColor,
  });

  final String label;
  final List<String> values;
  final ValueChanged<List<String>> onChanged;
  final String? hint;
  final Color? chipColor;
  final Color? chipTextColor;

  @override
  State<ChipInput> createState() => _ChipInputState();
}

class _ChipInputState extends State<ChipInput> {
  final _controller = TextEditingController();
  final _focus = FocusNode();

  @override
  void dispose() {
    _controller.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _add() {
    final raw = _controller.text.trim();
    if (raw.isEmpty) return;
    // Case-insensitive de-dup, preserving the user's original casing.
    if (widget.values.any((v) => v.toLowerCase() == raw.toLowerCase())) {
      _controller.clear();
      return;
    }
    widget.onChanged([...widget.values, raw]);
    _controller.clear();
    _focus.requestFocus();
  }

  void _remove(String value) =>
      widget.onChanged(widget.values.where((v) => v != value).toList());

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(widget.label,
            style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w700,
                color: scheme.onSurface)),
        const SizedBox(height: 8),
        if (widget.values.isNotEmpty) ...[
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final v in widget.values)
                _Chip(
                  label: v,
                  color: widget.chipColor ?? scheme.secondaryContainer,
                  textColor: widget.chipTextColor ?? scheme.onSecondaryContainer,
                  onRemove: () => _remove(v),
                ),
            ],
          ),
          const SizedBox(height: 10),
        ],
        Row(
          children: [
            Expanded(
              child: TextField(
                controller: _controller,
                focusNode: _focus,
                textInputAction: TextInputAction.done,
                onSubmitted: (_) => _add(),
                decoration: InputDecoration(
                  isDense: true,
                  hintText: widget.hint ?? 'Add…',
                  contentPadding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                ),
              ),
            ),
            const SizedBox(width: 8),
            IconButton.filledTonal(
              onPressed: _add,
              icon: const Icon(Icons.add),
              tooltip: 'Add',
            ),
          ],
        ),
      ],
    );
  }
}

class _Chip extends StatelessWidget {
  const _Chip({
    required this.label,
    required this.color,
    required this.textColor,
    required this.onRemove,
  });

  final String label;
  final Color color;
  final Color textColor;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.only(left: 12, right: 6, top: 6, bottom: 6),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(label,
              style: TextStyle(
                  fontSize: 13, color: textColor, fontWeight: FontWeight.w500)),
          const SizedBox(width: 4),
          InkWell(
            onTap: onRemove,
            customBorder: const CircleBorder(),
            child: Padding(
              padding: const EdgeInsets.all(2),
              child: Icon(Icons.close, size: 15, color: textColor),
            ),
          ),
        ],
      ),
    );
  }
}

/// A single-value formatted numeric field (salary floor), grouped with a label.
class LabeledField extends StatelessWidget {
  const LabeledField({
    super.key,
    required this.label,
    required this.child,
  });

  final String label;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label,
            style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w700,
                color: scheme.onSurface)),
        const SizedBox(height: 8),
        child,
      ],
    );
  }
}
