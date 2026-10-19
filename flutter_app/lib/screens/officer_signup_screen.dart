import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/api_client.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'citizen_signup_screen.dart';
import 'login_screen.dart';
import 'worker_signup_screen.dart';

/// "All zones" in the zone drop-down. It is sent to the backend as no zone.
const int allZones = 0;

const Map<String, String> fieldOptions = <String, String>{
  'water': 'Water supply',
  'sewerage': 'Sewerage',
  'billing': 'Billing and charges',
  'new_connection': 'New connections',
  'general': 'General grievances',
};

const Map<String, String> levelOptions = <String, String>{
  'depot': 'Depot',
  'deputy_ae': 'Deputy Area Engineer',
  'area_engineer': 'Area Engineer',
  'superintendent_engineer': 'Superintendent Engineer',
};

/// Officer sign-up. The officer can log in with the username and password straight away.
class OfficerSignupScreen extends StatefulWidget {
  const OfficerSignupScreen({super.key});

  @override
  State<OfficerSignupScreen> createState() => _OfficerSignupScreenState();
}

class _OfficerSignupScreenState extends State<OfficerSignupScreen> {
  final _name = TextEditingController();
  final _employeeId = TextEditingController();
  final _position = TextEditingController();
  final _mobile = TextEditingController();
  final _email = TextEditingController();
  final _username = TextEditingController();
  final _password = TextEditingController();
  final _password2 = TextEditingController();

  List<Map<String, dynamic>> _zones = <Map<String, dynamic>>[];
  int _zone = allZones;
  String? _field;
  String? _level;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadZones();
  }

  @override
  void dispose() {
    for (final controller in [_name, _employeeId, _position, _mobile, _email, _username, _password, _password2]) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _loadZones() async {
    try {
      final zones = await api.zones();
      if (mounted) setState(() => _zones = zones);
    } on ApiException {
      // The list stays on All zones.
    }
  }

  void _reset() {
    setState(() {
      for (final controller in [_name, _employeeId, _position, _mobile, _email, _username, _password, _password2]) {
        controller.clear();
      }
      _zone = allZones;
      _field = null;
      _level = null;
      _error = null;
    });
  }

  Future<void> _submit() async {
    if (_password.text != _password2.text) {
      setState(() => _error = 'The two passwords do not match.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final message = await api.officerSignUp(<String, dynamic>{
        'name': _name.text.trim(),
        'employee_id': _employeeId.text.trim(),
        'position': _position.text.trim(),
        'mobile': _mobile.text.trim(),
        'email': _email.text.trim(),
        'username': _username.text.trim(),
        'password': _password.text,
        'field': _field ?? '',
        'level': _level ?? '',
        'zone_number': _zone == allZones ? null : _zone,
      });
      if (!mounted) return;
      returnToLogin(context, message: message, officerTab: true);
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    void back() => returnToLogin(context);
    void officerLogin() => returnToLogin(context, officerTab: true);
    void workerLogin() => returnToLogin(context, workerTab: true);
    void citizenSignup() => Navigator.of(context).pushReplacement(
          MaterialPageRoute<void>(builder: (_) => const CitizenSignupScreen()),
        );
    void workerSignup() => Navigator.of(context).pushReplacement(
          MaterialPageRoute<void>(builder: (_) => const WorkerSignupScreen()),
        );
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              PortalTopBar(
                onBrandTap: back,
                iconLinks: true,
                links: [
                  NavLink('Home', back, icon: Icons.home_outlined),
                  NavLink('User Login', back, icon: Icons.person_outline),
                  NavLink('Worker Login', workerLogin, icon: Icons.engineering_outlined),
                  NavLink('Officer Login', officerLogin, icon: Icons.work_outline),
                ],
              ),
              const HeroBanner(
                compact: true,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    HeroHeadline(compact: true),
                    HeroLead(
                      'Officers see the complaints for their field, zone and level, act on them, and mark them resolved.',
                    ),
                    FeatureChips(),
                  ],
                ),
              ),
              NavStrip(
                links: [
                  NavLink('Home', back, icon: Icons.home_outlined),
                  NavLink('User Sign-up', citizenSignup, icon: Icons.person_outline),
                  NavLink('Worker Sign-up', workerSignup, icon: Icons.engineering_outlined),
                  NavLink('Officer Sign-up', () {}, selected: true, icon: Icons.work_outline),
                  NavLink('Log in', officerLogin, icon: Icons.login),
                ],
              ),
              PageWidth(
                child: FormCard(
                  icon: Icons.edit_note,
                  title: 'Officer Sign-up',
                  subtitle: 'Enter your details below. You can log in with your username and password once you sign up.',
                  footer: Wrap(
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      const Text('Already signed up?',
                          style: TextStyle(fontSize: 13.5, color: Palette.labelText)),
                      TextButton(onPressed: officerLogin, child: const Text('Log in as an officer')),
                    ],
                  ),
                  child: _form(),
                ),
              ),
              const PortalFooter(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _text(TextEditingController controller, String hint,
      {TextInputType? keyboard, bool obscure = false, List<TextInputFormatter>? formatters}) {
    return TextField(
      controller: controller,
      keyboardType: keyboard,
      obscureText: obscure,
      autocorrect: false,
      inputFormatters: formatters,
      decoration: fieldDecoration(hint: hint),
    );
  }

  Widget _form() {
    final error = _error;
    return TwoColumns(
      left: [
        LabeledField(label: 'Name', required: true, child: _text(_name, 'Enter your name')),
        LabeledField(label: 'Employee ID', required: true, child: _text(_employeeId, 'Enter your employee ID')),
        LabeledField(
          label: 'Position',
          required: true,
          child: _text(_position, 'Enter your position / designation'),
        ),
        LabeledField(
          label: 'Mobile number',
          required: true,
          child: _text(
            _mobile,
            'Enter your mobile number',
            keyboard: TextInputType.phone,
            formatters: [LengthLimitingTextInputFormatter(16)],
          ),
        ),
        LabeledField(
          label: 'E-mail address',
          required: true,
          child: _text(_email, 'Enter your email address', keyboard: TextInputType.emailAddress),
        ),
      ],
      right: [
        LabeledField(
          label: 'Zone',
          child: PortalDropdown<int>(
            value: _zone,
            hint: 'All zones',
            items: [
              const DropdownMenuItem<int>(value: allZones, child: Text('All zones')),
              for (final zone in _zones)
                if (zone['number'] is int)
                  DropdownMenuItem<int>(value: zone['number'] as int, child: Text('${zone['name']} zone')),
            ],
            onChanged: (value) => setState(() => _zone = value ?? allZones),
          ),
        ),
        LabeledField(
          label: 'Field you work in',
          required: true,
          child: PortalDropdown<String>(
            value: _field,
            hint: 'Select a field ...',
            items: [
              for (final entry in fieldOptions.entries)
                DropdownMenuItem<String>(value: entry.key, child: Text(entry.value)),
            ],
            onChanged: (value) => setState(() => _field = value),
          ),
        ),
        LabeledField(
          label: 'Level',
          required: true,
          child: PortalDropdown<String>(
            value: _level,
            hint: 'Select a level ...',
            items: [
              for (final entry in levelOptions.entries)
                DropdownMenuItem<String>(value: entry.key, child: Text(entry.value)),
            ],
            onChanged: (value) => setState(() => _level = value),
          ),
        ),
        LabeledField(
          label: 'Username',
          required: true,
          hint: 'Lower-case letters, numbers, dots, dashes and underscores.',
          child: _text(_username, 'For example: asha.depot'),
        ),
        LabeledField(
          label: 'Password',
          required: true,
          child: _text(_password, 'At least 10 characters', obscure: true),
        ),
        LabeledField(
          label: 'Confirm password',
          required: true,
          child: _text(_password2, 'Type the password again', obscure: true),
        ),
        if (error != null) ErrorText(error),
        const SizedBox(height: 18),
        Wrap(
          alignment: WrapAlignment.end,
          spacing: 14,
          runSpacing: 10,
          children: [
            PortalButton(label: 'Reset', icon: Icons.restart_alt, kind: ButtonKind.outline, onPressed: _reset),
            PortalButton(label: 'Submit', icon: Icons.send_outlined, busy: _busy, onPressed: _submit),
          ],
        ),
      ],
    );
  }
}
