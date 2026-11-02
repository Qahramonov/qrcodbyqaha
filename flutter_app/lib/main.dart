import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // No silent automatic retries: failed requests show an error with an explicit "Retry" button.
  runApp(ProviderScope(retry: (_, _) => null, child: const ChatHelperApp()));
}
