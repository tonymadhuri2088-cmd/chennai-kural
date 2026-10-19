import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../config.dart';
import 'cookie_store.dart';

/// A failed request. [status] is 0 when the server cannot be reached at all.
class ApiException implements Exception {
  const ApiException(this.status, this.message);

  final int status;
  final String message;

  @override
  String toString() => message;
}

/// Talks to the complaint portal backend. Every screen uses the one client named [api] below.
class ApiClient {
  ApiClient({http.Client? client, CookieStore? cookies})
      : _client = client ?? http.Client(),
        _cookies = cookies ?? CookieStore();

  final http.Client _client;
  final CookieStore _cookies;
  final String _base = apiBase();

  /// Call once at start-up, before the first request, so a saved login is used.
  Future<void> loadCookies() => _cookies.load();

  Future<Map<String, dynamic>> _send(String method, String path, [Map<String, dynamic>? body]) async {
    final headers = <String, String>{'Accept': 'application/json'};
    if (body != null) headers['Content-Type'] = 'application/json';
    if (!kIsWeb && _cookies.header.isNotEmpty) headers['Cookie'] = _cookies.header;

    final response = await _request(method, Uri.parse('$_base$path'), headers, body);

    final setCookie = response.headers['set-cookie'];
    if (!kIsWeb && setCookie != null) {
      await _cookies.apply(setCookie);
    }

    var data = <String, dynamic>{};
    if (response.body.isNotEmpty) {
      try {
        final decoded = jsonDecode(response.body);
        if (decoded is Map<String, dynamic>) data = decoded;
      } on FormatException {
        // Not JSON, for example an error page from a host. The status code below says what went wrong.
      }
    }
    if (response.statusCode >= 400) {
      final error = data['error'];
      final message = error is String ? error : 'Something went wrong. Try again.';
      throw ApiException(response.statusCode, message);
    }
    return data;
  }

  Future<http.Response> _request(
    String method,
    Uri uri,
    Map<String, String> headers,
    Map<String, dynamic>? body,
  ) async {
    try {
      if (method == 'GET') {
        return await _client.get(uri, headers: headers);
      }
      return await _client.post(uri, headers: headers, body: jsonEncode(body ?? <String, dynamic>{}));
    } catch (_) {
      throw const ApiException(0, 'Cannot reach the server. Check the address and your network, then try again.');
    }
  }

  /// The account behind this phone or browser: a citizen, a worker or an officer. Throws 401 when nobody is logged in.
  Future<Map<String, dynamic>> me() => _send('GET', '/api/me');

  /// The 15 zones, each with its wards, for the sign-up drop-downs.
  Future<List<Map<String, dynamic>>> zones() async {
    final data = await _send('GET', '/api/locations');
    final list = data['zones'] as List<dynamic>? ?? <dynamic>[];
    return list.cast<Map<String, dynamic>>().toList();
  }

  Future<String> citizenSignUp({
    required String name,
    required String mobile,
    required String address,
    required int wardNumber,
  }) async {
    final data = await _send('POST', '/api/citizen/signup', {
      'name': name,
      'contact': mobile,
      'address': address,
      'ward_number': wardNumber,
    });
    return data['message']?.toString() ?? 'Sign-up saved. Log in with your mobile number.';
  }

  /// Asks for a code. The backend returns it in the reply (demo mode, no SMS).
  Future<Map<String, dynamic>> citizenStartLogin(String mobile) =>
      _send('POST', '/api/citizen/login', {'contact': mobile});

  /// Checks the code and starts the login. Returns the citizen's profile.
  Future<Map<String, dynamic>> citizenVerify(String mobile, String code) =>
      _send('POST', '/api/citizen/verify', {'contact': mobile, 'code': code});

  Future<String> officerSignUp(Map<String, dynamic> fields) async {
    final data = await _send('POST', '/api/officer/signup', fields);
    return data['message']?.toString() ?? 'Sign-up received.';
  }

  Future<Map<String, dynamic>> officerLogin(String username, String password) =>
      _send('POST', '/api/officer/login', {'username': username, 'password': password});

  /// Matches an address to zones. Returns {matched, note, zones}.
  Future<Map<String, dynamic>> matchAddress(String address) =>
      _send('POST', '/api/citizen/match', {'address': address});

  /// Files a complaint for the logged-in citizen. [address] is where the problem is (the server uses the
  /// citizen's own address when it is null). [useLlm] asks the server to try the local model first;
  /// the keyword rules are always the fallback.
  Future<Map<String, dynamic>> registerComplaint(
    String text, {
    String? address,
    String landmark = '',
    bool useLlm = false,
  }) =>
      _send('POST', '/api/complaints', {
        'complaint': text,
        if (address != null) 'address': address,
        'landmark': landmark,
        'use_llm': useLlm,
      });

  /// Every complaint filed by the logged-in citizen, newest first.
  Future<List<Map<String, dynamic>>> citizenComplaints() async {
    final data = await _send('GET', '/api/citizen/complaints');
    return _list(data['complaints']);
  }

  /// One complaint with its history. Needs the complaint ID and the mobile number it was filed with.
  Future<Map<String, dynamic>> track(String id, String mobile) =>
      _send('POST', '/api/track', {'id': id, 'contact': mobile});

  /// The citizen says the problem is fixed (a code is returned to close it) or not fixed (it moves up).
  Future<Map<String, dynamic>> confirm(String id, String mobile, {required bool fixed, String comment = ''}) =>
      _send('POST', '/api/confirm', {'id': id, 'contact': mobile, 'fixed': fixed, 'comment': comment});

  /// Closes the complaint with the code shown after "Yes, it is fixed".
  Future<Map<String, dynamic>> confirmCode(String id, String mobile, String code) =>
      _send('POST', '/api/confirm-code', {'id': id, 'contact': mobile, 'code': code});

  Future<List<Map<String, dynamic>>> officerComplaints() async {
    final data = await _send('GET', '/api/officer/complaints');
    return _list(data['complaints']);
  }

  /// One complaint as the officer sees it, with what the officer may do.
  Future<Map<String, dynamic>> officerDetail(String id) =>
      _send('GET', '/api/officer/complaints/${Uri.encodeComponent(id)}');

  /// [action] is 'resolve', 'note' or 'escalate'. Every action needs a note.
  Future<Map<String, dynamic>> officerAction(String id, String action, String note) =>
      _send('POST', '/api/officer/complaints/${Uri.encodeComponent(id)}/$action', {'note': note});

  /// District Head Office only: moves on every complaint whose time limit has passed. Returns how many moved.
  Future<int> checkOverdue() async {
    final data = await _send('POST', '/api/officer/check-overdue', <String, dynamic>{});
    final moved = data['escalated'];
    return moved is List ? moved.length : 0;
  }

  /// Complaints that passed their time limit, with the citizen and any worker. The District Head Office sees all.
  Future<List<Map<String, dynamic>>> officerNotices() async {
    final data = await _send('GET', '/api/officer/notices');
    return _list(data['notices']);
  }

  // Workers

  /// Worker sign-up: the same details as a citizen, plus the department they work in.
  Future<String> workerSignUp({
    required String name,
    required String mobile,
    required String address,
    required int wardNumber,
    required String department,
  }) async {
    final data = await _send('POST', '/api/worker/signup', {
      'name': name,
      'contact': mobile,
      'address': address,
      'ward_number': wardNumber,
      'department': department,
    });
    return data['message']?.toString() ?? 'Sign-up saved. Log in with your mobile number on the Worker Login tab.';
  }

  /// Asks for a worker login code. The backend returns it in the reply (demo mode, no SMS).
  Future<Map<String, dynamic>> workerStartLogin(String mobile) =>
      _send('POST', '/api/worker/login', {'contact': mobile});

  /// Checks the code and starts the worker's login. Returns the worker's profile.
  Future<Map<String, dynamic>> workerVerify(String mobile, String code) =>
      _send('POST', '/api/worker/verify', {'contact': mobile, 'code': code});

  /// The worker's board: {available: complaints nobody has taken, mine: the worker's allotted tasks}.
  Future<Map<String, List<Map<String, dynamic>>>> workerBoard() async {
    final data = await _send('GET', '/api/worker/complaints');
    return {'available': _list(data['available']), 'mine': _list(data['mine'])};
  }

  /// Takes the complaint. The citizen then sees "Allotted" and "Work in progress".
  Future<Map<String, dynamic>> workerAccept(String id) =>
      _send('POST', '/api/worker/complaints/${Uri.encodeComponent(id)}/accept', <String, dynamic>{});

  /// Sends a code to the citizen's mobile. Returns {sent_to, minutes, note}.
  Future<Map<String, dynamic>> workerRequestCompletion(String id) =>
      _send('POST', '/api/worker/complaints/${Uri.encodeComponent(id)}/request-completion', <String, dynamic>{});

  /// Marks the complaint completed, only if [code] is the one the citizen received.
  Future<Map<String, dynamic>> workerComplete(String id, String code) =>
      _send('POST', '/api/worker/complaints/${Uri.encodeComponent(id)}/complete', {'code': code});

  List<Map<String, dynamic>> _list(Object? value) {
    if (value is! List) return <Map<String, dynamic>>[];
    return value.whereType<Map<String, dynamic>>().toList();
  }

  /// Ends the session on the server and forgets the saved cookies on this phone.
  Future<void> logout() async {
    try {
      await _send('POST', '/api/logout', <String, dynamic>{});
    } finally {
      await _cookies.clear();
    }
  }
}

/// The one client the whole app uses.
final ApiClient api = ApiClient();
