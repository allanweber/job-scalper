import 'package:flutter/material.dart';

/// Temporary tab body for M1 so the shell + navigation are reviewable. Each is
/// replaced by its real screen in later milestones (Feed=M3, Saved/Applications
/// =M6, Profile=M7).
class PlaceholderTab extends StatelessWidget {
  const PlaceholderTab({super.key, required this.title});

  final String title;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.construction_rounded, size: 40, color: scheme.onSurfaceVariant),
            const SizedBox(height: 12),
            Text('$title — coming in a later milestone',
                style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 14)),
          ],
        ),
      ),
    );
  }
}
