import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../theme.dart';
import '../widgets/account_button.dart';
import '../widgets/common.dart';
import '../widgets/router_panels.dart';
import '../widgets/your_complaints_panel.dart';
import 'login_screen.dart';
import 'track_complaint_screen.dart';

/// A service card on the home page opens this form with a matching example.
const Map<String, List<String>> serviceExamples = <String, List<String>>{
  'water': ['Water Supply', 'For example: no water has come to our street for three days.'],
  'leak': ['Leaks and Pipe Bursts', 'For example: water is leaking from the pipe in front of house number 12 since yesterday.'],
  'sewer': ['Sewer Blockage', 'For example: the sewer on our street is blocked and overflowing onto the road.'],
  'quality': ['Water Quality', 'For example: the tap water is brown and smells bad since Monday.'],
  'billing': ['Billing and Charges', 'For example: my water bill this month is much higher than usual.'],
  'connection': [
    'New Connections',
    'For example: I applied for a new water connection two months ago and nothing has happened.',
  ],
};

/// The Register Complaint form. Name, mobile number, address and ward come from the citizen's account.
class RegisterComplaintScreen extends StatefulWidget {
  const RegisterComplaintScreen({super.key, required this.profile, this.service});

  final Map<String, dynamic> profile;

  /// The service card that opened the form, for example 'leak'. Null when opened from the menu.
  final String? service;

  @override
  State<RegisterComplaintScreen> createState() => _RegisterComplaintScreenState();
}

class _RegisterComplaintScreenState extends State<RegisterComplaintScreen> {
  final _complaint = TextEditingController();
  late final TextEditingController _address = TextEditingController(text: _homeAddress);
  final _landmark = TextEditingController();
  bool _useLlm = true;
  bool _busy = false;
  int _refresh = 0; // goes up after a new complaint, so "Your complaints" loads again straight away
  String? _error;
  Map<String, dynamic>? _result;

  @override
  void initState() {
    super.initState();
    _complaint.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _complaint.dispose();
    _address.dispose();
    _landmark.dispose();
    super.dispose();
  }

  String _text(String key) => widget.profile[key]?.toString() ?? '';

  String get _homeAddress => _text('address');

  Future<void> _submit() async {
    if (_address.text.trim().length < 10) {
      setState(() => _error = 'Give the address of the problem, with the street and area.');
      return;
    }
    if (_complaint.text.trim().length < 10) {
      setState(() => _error = 'Describe the problem in at least 10 characters.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final view = await api.registerComplaint(
        _complaint.text.trim(),
        address: _address.text.trim(),
        landmark: _landmark.text.trim(),
        useLlm: _useLlm,
      );
      if (!mounted) return;
      setState(() {
        _result = view;
        _refresh++;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      if (error.status == 401) {
        returnToLogin(context, message: 'Your login has ended. Log in again.');
        return;
      }
      setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _reset() {
    setState(() {
      _address.text = _homeAddress;
      _landmark.clear();
      _complaint.clear();
      _useLlm = true;
      _error = null;
    });
  }

  void _another() {
    setState(() {
      _result = null;
      _address.text = _homeAddress;
      _landmark.clear();
      _complaint.clear();
    });
  }

  void _goHome() => Navigator.of(context).popUntil((route) => route.isFirst);

  Future<void> _logout() async {
    try {
      await api.logout();
    } catch (_) {
      // The session ends on this device either way.
    }
    if (mounted) returnToLogin(context);
  }

  @override
  Widget build(BuildContext context) {
    final example = serviceExamples[widget.service];
    final result = _result;
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              PortalTopBar(
                onBrandTap: _goHome,
                links: [
                  NavLink('Home', _goHome),
                  NavLink('Register Complaint', () {}, selected: true),
                  NavLink('Track Complaint', () {
                    Navigator.of(context).pushReplacement(
                      MaterialPageRoute<void>(builder: (_) => TrackComplaintScreen(profile: widget.profile)),
                    );
                  }),
                ],
                trailing: [
                  AccountButton(name: _text('name'), details: citizenDetails(widget.profile), onLogout: _logout),
                ],
              ),
              const HeroBanner(
                compact: true,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    HeroHeadline(compact: true),
                    HeroLead('Tell us what is wrong. The complaint goes to the officer for your field and ward.'),
                  ],
                ),
              ),
              PageWidth(child: _layout(example, result)),
              const PortalFooter(),
            ],
          ),
        ),
      ),
    );
  }

  /// The form, with "Your complaints" at the right on wide screens and under the form on narrow ones.
  Widget _layout(List<String>? example, Map<String, dynamic>? result) {
    final form = FormCard(
      icon: Icons.edit_note,
      title: 'Register Complaint',
      subtitle: 'Describe the problem below. Your name, mobile number and ward come from your account.',
      child: result == null ? _form(example) : _done(result),
    );
    final panel = YourComplaintsPanel(
      refresh: _refresh,
      onOpen: _trackThis,
      onLoginEnded: () => returnToLogin(context, message: 'Your login has ended. Log in again.'),
    );
    if (!isWideScreen(context)) {
      return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [form, panel]);
    }
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(child: form),
        const SizedBox(width: 22),
        SizedBox(width: 320, child: panel),
      ],
    );
  }

  Widget _form(List<String>? example) {
    final error = _error;
    return TwoColumns(
      left: [
        LabeledField(label: 'Name', child: ReadOnlyBox(value: _text('name'))),
        LabeledField(label: 'Mobile number', child: ReadOnlyBox(value: _text('mobile'))),
        LabeledField(
          label: 'Address of the problem',
          required: true,
          hint: 'Filled in with your address. Change it if the problem is somewhere else.',
          child: TextField(
            controller: _address,
            maxLength: 300,
            decoration: fieldDecoration(hint: 'House No. / Street / Area').copyWith(counterText: ''),
          ),
        ),
        LabeledField(
          label: 'Landmark',
          child: TextField(
            controller: _landmark,
            maxLength: 100,
            decoration: fieldDecoration(hint: 'For example: opposite the bus stop').copyWith(counterText: ''),
          ),
        ),
        LabeledField(
          label: 'Zone and ward',
          hint: 'From your account. The complaint goes to the officer for this ward.',
          child: ReadOnlyBox(value: '${_text('zone')}, ${_text('ward')}'),
        ),
      ],
      right: [
        if (example != null)
          NoticeBox(
            text: 'Service: ${example[0]}. The portal sorts the complaint from your description.',
            tone: NoticeTone.info,
          ),
        LabeledField(
          label: 'Describe the problem',
          required: true,
          hint: '${_complaint.text.length} of 2000 characters. Say where the problem is and since when.',
          child: TextField(
            controller: _complaint,
            minLines: 6,
            maxLines: 10,
            maxLength: 2000,
            decoration: InputDecoration(
              hintText: example != null ? example[1] : 'For example: no water has come to our street for three days.',
              counterText: '',
            ),
          ),
        ),
        CheckboxListTile(
          value: _useLlm,
          onChanged: (value) => setState(() => _useLlm = value ?? false),
          contentPadding: EdgeInsets.zero,
          controlAffinity: ListTileControlAffinity.leading,
          dense: true,
          title: const Text(
            'Use the local model to help sort the complaint, if it is running on the server computer',
            style: TextStyle(fontSize: TextSizes.label, color: Palette.labelText),
          ),
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

  void _trackThis(String id) {
    Navigator.of(context).pushReplacement(
      MaterialPageRoute<void>(builder: (_) => TrackComplaintScreen(profile: widget.profile, initialId: id)),
    );
  }

  /// After Submit: the complaint ID in a green box, a button to track it, and the "From the agents" box at the side.
  Widget _done(Map<String, dynamic> view) {
    String text(String key) => view[key]?.toString() ?? '';
    final id = text('id');
    final phone = isPhone(context);
    final rows = <MapEntry<String, String>>[
      MapEntry('Complaint ID', id),
      MapEntry('Type', text('complaint_label')),
      MapEntry('Field', text('field')),
      MapEntry('Status', text('status_text')),
      MapEntry('With', text('current_office')),
      MapEntry('Assigned to', text('assigned_to')),
      MapEntry('Address of the problem', text('problem_address').isEmpty ? 'Not given' : text('problem_address')),
      MapEntry('Landmark', text('landmark').isEmpty ? 'None' : text('landmark')),
      MapEntry('Zone and ward', '${text('zone')}, ${text('ward')}'),
      MapEntry('Time limit', formatWhen(view['deadline']?.toString())),
    ];
    final successBox = Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
      decoration: BoxDecoration(
        color: Palette.successBg,
        border: Border.all(color: const Color(0xFFB7DCC3)),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        children: [
          Icon(Icons.check_circle_outline, size: phone ? 34 : 44, color: Palette.success),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Your complaint is registered. Complaint ID:',
                  style: TextStyle(color: Palette.success, fontWeight: FontWeight.w600),
                ),
                SelectableText(
                  id,
                  style: TextStyle(
                    fontSize: phone ? 22 : 28,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 1,
                    color: Palette.navy,
                  ),
                ),
                const Text(
                  'Keep this complaint ID. Use it on Track Complaint to follow your complaint.',
                  style: TextStyle(fontSize: TextSizes.small, color: Palette.muted),
                ),
              ],
            ),
          ),
        ],
      ),
    );
    final agentsBox = Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 18),
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
      decoration: BoxDecoration(
        gradient: const LinearGradient(colors: [Color(0xFFF1F8FF), Color(0xFFE8F3FF)]),
        border: Border.all(color: Palette.primaryBright),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.auto_awesome_outlined, size: 22, color: Palette.primaryBright),
              SizedBox(width: 10),
              Text('From the agents', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700, color: Palette.navy)),
            ],
          ),
          const SizedBox(height: 6),
          const Text(
            'Message from the complaint router about this complaint.',
            style: TextStyle(fontSize: TextSizes.label, color: Palette.muted),
          ),
          const SizedBox(height: 10),
          // The router's message, as soon as the complaint is registered.
          RouterMessage(message: view['router_message']?.toString()),
        ],
      ),
    );
    return TwoColumns(
      left: [
        successBox,
        for (final row in rows)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(
                  width: 170,
                  child: Text(row.key, style: const TextStyle(fontSize: 14.5, color: Palette.muted)),
                ),
                Expanded(
                  child: Text(row.value, style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600)),
                ),
              ],
            ),
          ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 12,
          runSpacing: 10,
          children: [
            PortalButton(label: 'Track this complaint', icon: Icons.search, onPressed: () => _trackThis(id)),
            PortalButton(
              label: 'Register another',
              icon: Icons.edit_note,
              kind: ButtonKind.outline,
              onPressed: _another,
            ),
            PortalButton(label: 'Back to home', icon: Icons.home_outlined, kind: ButtonKind.outline, onPressed: _goHome),
          ],
        ),
      ],
      right: [
        agentsBox,
        if (view['router_progress'] is Map) ...[
          const Text(
            'Time limits for your complaint',
            style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: Palette.navy),
          ),
          const SizedBox(height: 8),
          RouterProgress(progress: view['router_progress']),
          const SizedBox(height: 14),
        ],
        const Text(
          'What happens next',
          style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: Palette.navy),
        ),
        const SizedBox(height: 8),
        const Text(
          '1. A field worker accepts your complaint. You will see "Allotted" and "Work in progress".\n'
          '2. When the work is done, a code comes to your mobile. Give it to the worker only if the problem is fixed.\n'
          '3. If the time limit passes, the officers get a notice and the complaint moves up to the next officer.',
          style: TextStyle(fontSize: TextSizes.label, color: Palette.muted, height: 1.7),
        ),
      ],
    );
  }
}
