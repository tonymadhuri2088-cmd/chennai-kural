import 'package:flutter/material.dart';

import '../api/api_client.dart';
import 'home_screen.dart';
import 'login_screen.dart';
import 'officer_home_screen.dart';
import 'worker_home_screen.dart';

/// Opens first. If someone is still logged in on this phone or browser, it goes straight to their screen.
class StartScreen extends StatefulWidget {
  const StartScreen({super.key});

  @override
  State<StartScreen> createState() => _StartScreenState();
}

class _StartScreenState extends State<StartScreen> {
  @override
  void initState() {
    super.initState();
    _check();
  }

  Future<void> _check() async {
    Widget next = const LoginScreen();
    try {
      await api.loadCookies();
      final me = await api.me();
      if (me['role'] == 'citizen') {
        next = HomeScreen(profile: me);
      } else if (me['role'] == 'officer') {
        next = OfficerHomeScreen(officer: me);
      } else if (me['role'] == 'worker') {
        next = WorkerHomeScreen(worker: me);
      }
    } catch (_) {
      // Nobody is logged in, or the server cannot be reached yet. Show the first screen.
    }
    if (!mounted) return;
    Navigator.of(context).pushReplacement(MaterialPageRoute(builder: (_) => next));
  }

  @override
  Widget build(BuildContext context) {
    return const Scaffold(body: Center(child: CircularProgressIndicator()));
  }
}
