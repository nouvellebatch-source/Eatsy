import 'package:material_ui/material_ui.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:eatsy/main.dart';

void main() {
  testWidgets('EatsyApp smoke test', (WidgetTester tester) async {
    // Build our app and trigger a frame.
    await tester.pumpWidget(const EatsyApp());

    // Pump to allow FutureBuilder to complete.
    await tester.pumpAndSettle();

    // Verify that app loaded.
    expect(find.byType(MaterialApp), findsOneWidget);
  });
}
