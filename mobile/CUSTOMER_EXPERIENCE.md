# Customer experience preview

The existing `lib/main.dart` customer and administrator application is intentionally preserved. The expanded customer flow is available as a separate Flutter entry point while it is reviewed and integrated:

```sh
cd mobile
flutter pub get
flutter run -t lib/customer_experience_main.dart
```

This preview reuses the existing menu context, product model, session/login, API URL, currency formatter, and order submission helper from `lib/main.dart`. Its delivery mode and card are presentation-only: the current Eatsy API does not support delivery fulfillment or card payment, and orders are submitted as dine-in/cash through the existing API contract. Product extras are shown in the product detail UI but are not included in order submission because the current order API validates extras against restaurant catalog products.
