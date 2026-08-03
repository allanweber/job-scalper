import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../state/session.dart';

/// Profile → Appearance. Chooses the app theme; persisted via the session.
class AppearanceScreen extends ConsumerWidget {
  const AppearanceScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final mode = ref.watch(sessionProvider).themeMode;
    final session = ref.read(sessionProvider.notifier);

    return Scaffold(
      appBar: AppBar(title: const Text('Appearance')),
      body: RadioGroup<ThemeMode>(
        groupValue: mode,
        onChanged: (v) {
          if (v != null) session.setThemeMode(v);
        },
        child: ListView(
          padding: const EdgeInsets.symmetric(vertical: 8),
          children: [
            for (final option in const [
              (
                ThemeMode.system,
                'System default',
                Icons.brightness_auto_rounded
              ),
              (ThemeMode.light, 'Light', Icons.light_mode_rounded),
              (ThemeMode.dark, 'Dark', Icons.dark_mode_rounded),
            ])
              RadioListTile<ThemeMode>(
                value: option.$1,
                secondary: Icon(option.$3),
                title: Text(option.$2),
              ),
          ],
        ),
      ),
    );
  }
}
