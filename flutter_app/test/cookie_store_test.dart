import 'package:flutter_test/flutter_test.dart';

import 'package:chennai_complaints/api/cookie_store.dart';

void main() {
  test('stores the session cookie the server sends', () {
    final jar = applySetCookie(
      <String, String>{},
      'citizen_session=abc123; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000',
    );
    expect(jar, {'citizen_session': 'abc123'});
  });

  test('removes a cookie the server expires at logout', () {
    final jar = applySetCookie(
      <String, String>{'citizen_session': 'abc123'},
      'citizen_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0',
    );
    expect(jar, isEmpty);
  });

  test('reads two cookies that the HTTP client joined with a comma', () {
    final jar = applySetCookie(
      <String, String>{},
      'citizen_session=; Path=/; Max-Age=0, portal_session=xyz; Path=/; HttpOnly; Max-Age=3600',
    );
    expect(jar, {'portal_session': 'xyz'});
  });

  test('reads two cookies joined with a comma and no space, as package:http does on phones', () {
    final jar = applySetCookie(
      <String, String>{'citizen_session': 'abc123'},
      'citizen_session=; Path=/; Max-Age=0,portal_session=; Path=/; Max-Age=0',
    );
    expect(jar, isEmpty);
  });

  test('keeps the comma inside a cookie date', () {
    final jar = applySetCookie(
      <String, String>{},
      'citizen_session=abc123; Expires=Wed, 21 Oct 2026 07:28:00 GMT; Path=/',
    );
    expect(jar, {'citizen_session': 'abc123'});
  });
}
