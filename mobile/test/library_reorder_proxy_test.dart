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

  testWidgets('proxy stays flat with elevation 0 and scale 1.0 when not lifted', (
    tester,
  ) async {
    final liftedNotifier = ValueNotifier<bool>(false);
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
              const SizedBox(width: 40, height: 20, key: Key('row2')),
              0,
              const AlwaysStoppedAnimation<double>(1),
              colorScheme: scheme,
              isLifted: liftedNotifier,
            );
            return Scaffold(body: proxy);
          },
        ),
      ),
    );
    await tester.pumpAndSettle();
    final material = tester.widget<Material>(find.byType(Material).last);
    expect(material.elevation, 0.0);
    final transform = tester.widget<Transform>(find.byKey(const Key('reorder_proxy_transform')));
    expect(transform.transform.getMaxScaleOnAxis(), 1.0);

    // Now trigger motion lift
    liftedNotifier.value = true;
    await tester.pumpAndSettle();
    final liftedMaterial = tester.widget<Material>(find.byType(Material).last);
    expect(liftedMaterial.elevation, 10.0);
    final liftedTransform = tester.widget<Transform>(find.byKey(const Key('reorder_proxy_transform')));
    expect(liftedTransform.transform.getMaxScaleOnAxis(), closeTo(1.04, 0.001));
  });
}
