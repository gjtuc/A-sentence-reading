import 'package:flutter/material.dart';

import 'app.dart';
import 'services/error_reporter.dart';
import 'state/auth_controller.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // design/130 — install early so bootstrap errors are reportable after auth.
  final auth = AuthController();
  asrErrorReporter = ErrorReporter(client: auth.client)..install();
  runApp(SentenceReadingApp(auth: auth));
}
