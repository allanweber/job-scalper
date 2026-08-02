import 'package:flutter/material.dart';

/// A settings-list row: leading icon, title, optional subtitle, chevron. Used
/// across the Profile hub and its sub-screens. [danger] tints it for
/// destructive actions.
class SettingsTile extends StatelessWidget {
  const SettingsTile({
    super.key,
    required this.icon,
    required this.title,
    this.subtitle,
    this.onTap,
    this.danger = false,
    this.trailing,
  });

  final IconData icon;
  final String title;
  final String? subtitle;
  final VoidCallback? onTap;
  final bool danger;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final color = danger ? scheme.error : scheme.onSurface;
    return ListTile(
      leading: Icon(icon, color: danger ? scheme.error : scheme.primary),
      title: Text(title,
          style: TextStyle(
              fontSize: 15, fontWeight: FontWeight.w600, color: color)),
      subtitle: subtitle == null
          ? null
          : Text(subtitle!,
              style: TextStyle(fontSize: 12.5, color: scheme.onSurfaceVariant)),
      trailing: trailing ??
          (onTap == null
              ? null
              : Icon(Icons.chevron_right_rounded,
                  color: scheme.onSurfaceVariant)),
      onTap: onTap,
    );
  }
}
