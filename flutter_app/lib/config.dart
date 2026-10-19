import 'package:flutter/foundation.dart';

/// The name shown at the top of every screen. It is not the name of any government portal.
const String appName = 'Chennai Complaint Portal';

/// Where the backend runs.
///
/// - Web served by the backend (http://127.0.0.1:8000/app/): leave empty, the site is the same.
/// - Android emulator: the computer is reached at 10.0.2.2 by default.
/// - iPhone simulator: localhost by default.
/// - A real phone: pass your computer's Wi-Fi address, for example
///   flutter run --dart-define=API_BASE=http://192.168.1.20:8000
String apiBase() {
  const fromBuild = String.fromEnvironment('API_BASE', defaultValue: '');
  if (fromBuild.isNotEmpty) return fromBuild;
  if (kIsWeb) return '';
  if (defaultTargetPlatform == TargetPlatform.android) return 'http://10.0.2.2:8000';
  return 'http://localhost:8000';
}
