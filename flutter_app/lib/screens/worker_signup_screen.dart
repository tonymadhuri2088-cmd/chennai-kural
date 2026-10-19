import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/api_client.dart';
import '../theme.dart';
import '../widgets/common.dart';
import 'citizen_signup_screen.dart';
import 'login_screen.dart';
import 'officer_signup_screen.dart';

/// Departments a worker can pick with one tap. They can also type their own.
const List<String> workerDepartments = <String>[
  'Water supply',
  'Sewerage',
  'Billing and charges',
  'New connections',
  'Plumbing and repairs',
  'General maintenance',
];

/// Worker sign-up: the same details as a citizen, plus the department they work in.
class WorkerSignupScreen extends StatefulWidget {
  const WorkerSignupScreen({super.key});

  @override
  State<WorkerSignupScreen> createState() => _WorkerSignupScreenState();
}

class _WorkerSignupScreenState extends State<WorkerSignupScreen> {
  final _name = TextEditingController();
  final _address = TextEditingController();
  final _mobile = TextEditingController();
  final _department = TextEditingController();
  final _addressFocus = FocusNode();

  List<Map<String, dynamic>> _zones = <Map<String, dynamic>>[];
  bool _zonesFailed = false;
  int? _zone;
  int? _ward;
  String? _matchNote;
  String _lastMatched = '';
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadZones();
    _department.addListener(() => setState(() {}));
    // When the address field is left, suggest the zone the address matches.
    _addressFocus.addListener(() {
      if (!_addressFocus.hasFocus) _matchAddress();
    });
  }

  @override
  void dispose() {
    _name.dispose();
    _address.dispose();
    _mobile.dispose();
    _department.dispose();
    _addressFocus.dispose();
    super.dispose();
  }

  Future<void> _loadZones() async {
    try {
      final zones = await api.zones();
      if (!mounted) return;
      setState(() {
        _zones = zones;
        _zonesFailed = false;
      });
    } on ApiException {
      if (mounted) setState(() => _zonesFailed = true);
    }
  }

  List<Map<String, dynamic>> get _wards {
    for (final zone in _zones) {
      if (zone['number'] == _zone) {
        final wards = zone['wards'];
        if (wards is List) return wards.whereType<Map<String, dynamic>>().toList();
      }
    }
    return <Map<String, dynamic>>[];
  }

  Future<void> _matchAddress() async {
    final address = _address.text.trim();
    if (address.length < 10 || address == _lastMatched || _zones.isEmpty) return;
    _lastMatched = address;
    try {
      final view = await api.matchAddress(address);
      if (!mounted) return;
      final matched = view['matched'] == true;
      final zones = view['zones'];
      setState(() {
        if (matched && zones is List && zones.isNotEmpty && _zone == null) {
          final first = zones.first;
          if (first is Map<String, dynamic> && first['number'] is int) {
            _zone = first['number'] as int;
            _ward = null;
          }
        }
        _matchNote = matched
            ? view['note']?.toString()
            : 'No zone name in your address matched. Choose your zone from the list.';
      });
    } on ApiException {
      if (mounted) setState(() => _matchNote = null);
    }
  }

  void _reset() {
    setState(() {
      _name.clear();
      _address.clear();
      _mobile.clear();
      _department.clear();
      _zone = null;
      _ward = null;
      _matchNote = null;
      _lastMatched = '';
      _error = null;
    });
  }

  Future<void> _submit() async {
    final ward = _ward;
    if (ward == null) {
      setState(() => _error = 'Choose your zone, then your ward.');
      return;
    }
    if (_department.text.trim().length < 2) {
      setState(() => _error = 'Enter the department you work in.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final message = await api.workerSignUp(
        name: _name.text.trim(),
        mobile: _mobile.text.trim(),
        address: _address.text.trim(),
        wardNumber: ward,
        department: _department.text.trim(),
      );
      if (!mounted) return;
      returnToLogin(context, message: message, workerTab: true);
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    void back() => returnToLogin(context);
    void workerLogin() => returnToLogin(context, workerTab: true);
    void officerLogin() => returnToLogin(context, officerTab: true);
    void userSignup() => Navigator.of(context).pushReplacement(
          MaterialPageRoute<void>(builder: (_) => const CitizenSignupScreen()),
        );
    void officerSignup() => Navigator.of(context).pushReplacement(
          MaterialPageRoute<void>(builder: (_) => const OfficerSignupScreen()),
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
                    HeroLead('Sign up as a field worker. Accept complaints, fix the problem, and close each one '
                        "with the citizen's code."),
                    FeatureChips(),
                  ],
                ),
              ),
              NavStrip(
                links: [
                  NavLink('Home', back, icon: Icons.home_outlined),
                  NavLink('User Sign-up', userSignup, icon: Icons.person_outline),
                  NavLink('Worker Sign-up', () {}, selected: true, icon: Icons.engineering_outlined),
                  NavLink('Officer Sign-up', officerSignup, icon: Icons.work_outline),
                  NavLink('Log in', workerLogin, icon: Icons.login),
                ],
              ),
              PageWidth(
                child: FormCard(
                  icon: Icons.engineering_outlined,
                  title: 'Worker Sign-up',
                  subtitle: 'Enter your details below to create your account.',
                  footer: Wrap(
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      const Text('Already signed up?', style: TextStyle(fontSize: 13.5, color: Palette.labelText)),
                      TextButton(onPressed: workerLogin, child: const Text('Log in with your mobile number')),
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

  Widget _form() {
    final error = _error;
    final note = _matchNote;
    final wards = _wards;
    final typed = _department.text.trim().toLowerCase();
    return TwoColumns(
      left: [
        LabeledField(
          label: 'Name',
          required: true,
          child: TextField(controller: _name, decoration: fieldDecoration(hint: 'Enter your name')),
        ),
        LabeledField(
          label: 'Address',
          required: true,
          hint: 'Used to find your zone. Include your area name.',
          child: TextField(
            controller: _address,
            focusNode: _addressFocus,
            decoration: fieldDecoration(hint: 'House No. / Street / Area'),
            onSubmitted: (_) => _matchAddress(),
          ),
        ),
        LabeledField(
          label: 'Zone',
          required: true,
          hint: note,
          child: PortalDropdown<int>(
            value: _zone,
            hint: _zonesFailed ? 'Zones could not be loaded. Go back and try again.' : 'Select a zone ...',
            items: [
              for (final zone in _zones)
                if (zone['number'] is int)
                  DropdownMenuItem<int>(value: zone['number'] as int, child: Text('${zone['name']} zone')),
            ],
            onChanged: _zones.isEmpty
                ? null
                : (value) => setState(() {
                      _zone = value;
                      _ward = null;
                    }),
          ),
        ),
        LabeledField(
          label: 'Ward (Greater Chennai Corporation)',
          required: true,
          child: PortalDropdown<int>(
            value: _ward,
            hint: 'Select your ward ...',
            disabledHint: 'Select a zone first',
            items: [
              for (final ward in wards)
                if (ward['number'] is int)
                  DropdownMenuItem<int>(value: ward['number'] as int, child: Text(ward['label']?.toString() ?? '')),
            ],
            onChanged: wards.isEmpty ? null : (value) => setState(() => _ward = value),
          ),
        ),
      ],
      right: [
        const LabeledField(label: 'Country', child: ReadOnlyBox(value: 'India')),
        const LabeledField(label: 'State', child: ReadOnlyBox(value: 'Tamil Nadu')),
        const LabeledField(label: 'District', child: ReadOnlyBox(value: 'Chennai')),
        LabeledField(
          label: 'Mobile number',
          required: true,
          hint: 'You log in with a code to this number.',
          child: TextField(
            controller: _mobile,
            keyboardType: TextInputType.phone,
            inputFormatters: [LengthLimitingTextInputFormatter(16)],
            decoration: fieldDecoration(hint: 'Enter your 10-digit mobile number'),
          ),
        ),
        LabeledField(
          label: 'Department of work',
          required: true,
          hint: 'Type your department, or tap one below.',
          child: TextField(
            controller: _department,
            maxLength: 60,
            decoration: fieldDecoration(hint: 'Enter your department of work', icon: Icons.apartment_outlined)
                .copyWith(counterText: ''),
          ),
        ),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final name in workerDepartments)
              ChoiceChip(
                label: Text(name),
                selected: typed == name.toLowerCase(),
                onSelected: (_) => _department.text = name,
                labelStyle: const TextStyle(fontSize: TextSizes.small),
                visualDensity: VisualDensity.compact,
              ),
          ],
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
