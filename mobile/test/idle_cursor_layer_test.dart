import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sentence_reading/widgets/idle_cursor_layer.dart';

void main() {
  testWidgets('design/423: a clickable spot under a resting pointer loses its cursor too',
      (tester) async {
    var taps = 0;
    Widget app(bool hidden) => MaterialApp(
          home: IdleCursorLayer(
            hidden: hidden,
            child: Center(
              child: MouseRegion(
                cursor: SystemMouseCursors.click,
                child: GestureDetector(
                  onTap: () => taps++,
                  child: const SizedBox(width: 120, height: 60, child: Text('go')),
                ),
              ),
            ),
          ),
        );

    await tester.pumpWidget(app(false));
    final mouse = await tester.createGesture(kind: PointerDeviceKind.mouse, pointer: 1);
    await mouse.addPointer(location: Offset.zero);
    await mouse.moveTo(tester.getCenter(find.text('go')));
    await tester.pump();
    MouseCursor? cursor() => RendererBinding.instance.mouseTracker.debugDeviceActiveCursor(1);
    expect(cursor(), SystemMouseCursors.click);

    await tester.pumpWidget(app(true));
    await tester.pump();
    expect(cursor(), SystemMouseCursors.none, reason: 'no move needed');

    await tester.tap(find.text('go'), kind: PointerDeviceKind.mouse);
    expect(taps, 1, reason: 'the layer lets clicks through');

    await tester.pumpWidget(app(false));
    await tester.pump();
    expect(cursor(), SystemMouseCursors.click);
    await mouse.removePointer();
  });
}
