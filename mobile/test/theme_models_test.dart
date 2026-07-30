import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/theme_models.dart';
import 'package:sentence_reading/api/theme_store.dart';
import 'package:sentence_reading/state/theme_controller.dart';

void main() {
  group('parseThemeModePref', () {
    test('happy', () {
      expect(parseThemeModePref('system'), ThemeMode.system);
      expect(parseThemeModePref('light'), ThemeMode.light);
      expect(parseThemeModePref('dark'), ThemeMode.dark);
      expect(parseThemeModePref('LIGHT'), ThemeMode.light);
    });

    test('edges', () {
      expect(parseThemeModePref(null), ThemeMode.system);
      expect(parseThemeModePref(''), ThemeMode.system);
      expect(parseThemeModePref('   '), ThemeMode.system);
      expect(parseThemeModePref('nope'), ThemeMode.system);
      expect(parseThemeModePref('lite'), ThemeMode.light);
      expect(parseThemeModePref('night'), ThemeMode.dark);
      expect(parseThemeModePref('auto'), ThemeMode.system);
    });
  });

  group('serializeThemeModePref', () {
    test('roundtrip', () {
      for (final m in ThemeMode.values) {
        expect(parseThemeModePref(serializeThemeModePref(m)), m);
      }
    });
  });

  group('ThemeController + MemoryThemeStore', () {
    test('bootstrap default and persist', () async {
      final store = MemoryThemeStore();
      final c = ThemeController(store: store);
      await c.bootstrap();
      expect(c.mode, ThemeMode.system);
      expect(c.ready, isTrue);

      await c.setMode(ThemeMode.dark);
      expect(c.mode, ThemeMode.dark);
      expect(await store.readRaw(), 'dark');

      final c2 = ThemeController(store: store);
      await c2.bootstrap();
      expect(c2.mode, ThemeMode.dark);
    });

    test('corrupt store value becomes system', () async {
      final store = MemoryThemeStore();
      await store.writeRaw('!!!garbage!!!');
      final c = ThemeController(store: store);
      await c.bootstrap();
      expect(c.mode, ThemeMode.system);
    });
  });
}
