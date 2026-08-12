/// design/122 — library reorder proxy must not use M3 white surface tint.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/api/library_reorder_proxy.dart';

void main() {
  testWidgets('proxy uses theme surface and transparent surfaceTint', (
    tester,
  ) async {
    late Material material;
    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData(
          useMaterial3: true,
          colorScheme: ColorScheme.fromSeed(seedColor: Colors.teal),
        ),
        home: Builder(
          builder: (context) {
            final scheme = Theme.of(context).colorScheme;
            final proxy = libraryReorderProxyDecorator(
              const SizedBox(width: 40, height: 20, key: Key('row')),
              0,
              const AlwaysStoppedAnimation<double>(1),
              colorScheme: scheme,
            );
            return Scaffold(body: proxy);
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    material = tester.widget<Material>(find.byType(Material).last);
    expect(material.surfaceTintColor, Colors.transparent);
    expect(material.color, isNotNull);
    // Fail-closed: must not be forced opaque white independent of theme.
    expect(material.color, isNot(equals(const Color(0xFFFFFFFF))));
    expect(find.byKey(const Key('row')), findsOneWidget);
  });
}
