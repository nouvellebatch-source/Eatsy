import 'package:flutter/widgets.dart';

import 'customer_experience.dart';

/// Run the new customer experience without replacing the existing app entrypoint:
/// `flutter run -t lib/customer_experience_main.dart`.
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const EatsyCustomerExperience());
}
