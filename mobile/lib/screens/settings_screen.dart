import 'package:flutter/material.dart';

import '../api/theme_models.dart';
import '../state/theme_controller.dart';

/// App settings: theme only for 0.2.74 (design/66).
///
/// Live Enable / IPS: Trading Gate (ASR out).
class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key, required this.theme});

  final ThemeController theme;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: theme,
      builder: (context, _) {
        if (!theme.ready) {
          return const Center(child: CircularProgressIndicator());
        }
        return ListView(
          padding: const EdgeInsets.all(24),
          children: [
            Text('설정', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 8),
            Text(
              '화면 밝기. 선택값은 재실행 후에도 유지됩니다.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 16),
            Text('테마', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 12),
            SegmentedButton<ThemeMode>(
              segments: const [
                ButtonSegment(
                  value: ThemeMode.system,
                  label: Text('시스템'),
                  icon: Icon(Icons.brightness_auto),
                ),
                ButtonSegment(
                  value: ThemeMode.light,
                  label: Text('밝음'),
                  icon: Icon(Icons.light_mode),
                ),
                ButtonSegment(
                  value: ThemeMode.dark,
                  label: Text('어둠'),
                  icon: Icon(Icons.dark_mode),
                ),
              ],
              selected: {theme.mode},
              onSelectionChanged: (set) {
                if (set.isEmpty) return; // EDGE: empty selection
                theme.setMode(set.first);
              },
            ),
            const SizedBox(height: 12),
            Text(
              '현재: ${themeModeLabelKo(theme.mode)}',
              style: Theme.of(context).textTheme.bodyMedium,
            ),
            if (theme.error != null) ...[
              const SizedBox(height: 8),
              Text(
                theme.error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error),
              ),
            ],
            const SizedBox(height: 32),
            Text(
              'Live Enable / IPS: Trading Gate (ASR out)',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        );
      },
    );
  }
}
