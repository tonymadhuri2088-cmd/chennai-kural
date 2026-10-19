import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

/// Keeps the session cookies on a phone, so the user stays logged in until they log out.
/// Browsers keep their own cookies, so the web build does not use this class.
class CookieStore {
  static const String _key = 'session_cookies';

  Map<String, String> _jar = <String, String>{};

  /// The Cookie header to send, for example "citizen_session=abc".
  String get header => _jar.entries.map((entry) => '${entry.key}=${entry.value}').join('; ');

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_key);
    if (raw == null || raw.isEmpty) {
      _jar = <String, String>{};
      return;
    }
    final decoded = jsonDecode(raw);
    if (decoded is Map) {
      _jar = decoded.map((key, value) => MapEntry(key.toString(), value.toString()));
    } else {
      _jar = <String, String>{};
    }
  }

  Future<void> apply(String setCookie) async {
    _jar = applySetCookie(_jar, setCookie);
    await _save();
  }

  Future<void> clear() async {
    _jar = <String, String>{};
    await _save();
  }

  Future<void> _save() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_key, jsonEncode(_jar));
  }
}

/// Reads the Set-Cookie header and returns the updated cookies.
///
/// The HTTP client joins several Set-Cookie lines with a comma (with or without a space). The split only breaks before
/// something that looks like "name=", so the commas inside cookie dates are left alone.
/// A cookie with Max-Age=0 (or an empty value) is removed.
Map<String, String> applySetCookie(Map<String, String> jar, String setCookie) {
  final result = Map<String, String>.from(jar);
  for (final item in setCookie.split(RegExp(r',\s*(?=[A-Za-z0-9_-]+=)'))) {
    final parts = item.split(';');
    final pair = parts.first.trim();
    final at = pair.indexOf('=');
    if (at <= 0) continue;
    final name = pair.substring(0, at).trim();
    final value = pair.substring(at + 1).trim();
    final expired = parts.any((part) => part.trim().toLowerCase() == 'max-age=0');
    if (expired || value.isEmpty) {
      result.remove(name);
    } else {
      result[name] = value;
    }
  }
  return result;
}
