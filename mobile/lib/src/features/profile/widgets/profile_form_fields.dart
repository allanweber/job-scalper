import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../data/models/account_models.dart';
import '../../onboarding/widgets/chip_input.dart';

/// The editable match-profile form: target titles, skills, keywords, salary
/// floor and remote-only. Controllerless — it takes a [Profile] value and
/// reports every edit through [onChanged], so both the onboarding review step
/// and the Profile → Search profile editor render the same fields.
class ProfileFormFields extends StatefulWidget {
  const ProfileFormFields({
    super.key,
    required this.value,
    required this.onChanged,
  });

  final Profile value;
  final ValueChanged<Profile> onChanged;

  @override
  State<ProfileFormFields> createState() => _ProfileFormFieldsState();
}

class _ProfileFormFieldsState extends State<ProfileFormFields> {
  late final TextEditingController _salary;

  @override
  void initState() {
    super.initState();
    final f = widget.value.salaryFloor;
    _salary = TextEditingController(text: f > 0 ? f.toStringAsFixed(0) : '');
  }

  @override
  void dispose() {
    _salary.dispose();
    super.dispose();
  }

  Profile get _p => widget.value;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ChipInput(
          label: 'Target titles',
          hint: 'e.g. Backend Engineer',
          values: _p.titles,
          onChanged: (v) => widget.onChanged(_p.copyWith(titles: v)),
        ),
        const SizedBox(height: 22),
        ChipInput(
          label: 'Required skills',
          hint: 'e.g. Python',
          values: _p.requiredSkills,
          onChanged: (v) => widget.onChanged(_p.copyWith(requiredSkills: v)),
        ),
        const SizedBox(height: 22),
        ChipInput(
          label: 'Nice-to-have skills',
          hint: 'e.g. Kubernetes',
          values: _p.niceToHaveSkills,
          onChanged: (v) => widget.onChanged(_p.copyWith(niceToHaveSkills: v)),
        ),
        const SizedBox(height: 22),
        ChipInput(
          label: 'Keywords',
          hint: 'e.g. fintech',
          values: _p.keywords,
          onChanged: (v) => widget.onChanged(_p.copyWith(keywords: v)),
        ),
        const SizedBox(height: 22),
        ChipInput(
          label: 'Exclude keywords',
          hint: 'e.g. on-site',
          values: _p.excludeKeywords,
          onChanged: (v) => widget.onChanged(_p.copyWith(excludeKeywords: v)),
        ),
        const SizedBox(height: 22),
        LabeledField(
          label: 'Minimum salary (USD / year)',
          child: TextField(
            controller: _salary,
            keyboardType: TextInputType.number,
            inputFormatters: [FilteringTextInputFormatter.digitsOnly],
            style: const TextStyle(fontFamily: 'RobotoMono'),
            decoration: const InputDecoration(
              isDense: true,
              prefixText: '\$ ',
              hintText: '0',
              contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 12),
            ),
            onChanged: (v) => widget.onChanged(
                _p.copyWith(salaryFloor: double.tryParse(v) ?? 0)),
          ),
        ),
        const SizedBox(height: 8),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: Text('Remote only',
              style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w600,
                  color: scheme.onSurface)),
          subtitle: Text('Only show fully-remote roles',
              style: TextStyle(fontSize: 12, color: scheme.onSurfaceVariant)),
          value: _p.remoteOnly,
          onChanged: (v) => widget.onChanged(_p.copyWith(remoteOnly: v)),
        ),
      ],
    );
  }
}
