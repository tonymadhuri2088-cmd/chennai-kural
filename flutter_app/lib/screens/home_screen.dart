import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/api_client.dart';
import '../theme.dart';
import '../widgets/account_button.dart';
import '../widgets/board.dart';
import '../widgets/common.dart';
import 'login_screen.dart';
import 'register_complaint_screen.dart';
import 'track_complaint_screen.dart';

class _Service {
  const _Service(this.key, this.title, this.text, this.icon, this.tone);

  final String key;
  final String title;
  final String text;
  final IconData icon;
  final Tone tone;
}

const List<_Service> _services = <_Service>[
  _Service('water', 'Water Supply', 'No water, low pressure or an irregular supply.', Icons.water_drop_outlined, Tone.blue),
  _Service('leak', 'Leaks and Pipe Bursts', 'A leaking or burst water pipe on your street.', Icons.build_outlined, Tone.orange),
  _Service('sewer', 'Sewer Blockage', 'A blocked, overflowing or damaged sewer line.', Icons.plumbing, Tone.purple),
  _Service('quality', 'Water Quality', 'Dirty, smelly or contaminated water.', Icons.warning_amber_rounded, Tone.teal),
  _Service('billing', 'Billing and Charges', 'A wrong bill, tax or unfair charge.', Icons.receipt_long_outlined, Tone.yellow),
  _Service('connection', 'New Connections', 'A delay in a new water or sewer connection.', Icons.home_outlined, Tone.green),
];

class _Step {
  const _Step(this.title, this.text, this.icon, this.tone);

  final String title;
  final String text;
  final IconData icon;
  final Tone tone;
}

const List<_Step> _steps = <_Step>[
  _Step('1. Register', 'Describe the problem. Your name, mobile number and ward are filled in.', Icons.edit_note, Tone.blue),
  _Step('2. Auto-route', 'It goes to the officer for your field and ward.', Icons.alt_route, Tone.purple),
  _Step('3. Track', 'See which office has it and its time limit.', Icons.search, Tone.green),
  _Step('4. Get Resolved', 'Confirm the fix, or send it up if it is not fixed.', Icons.check_circle_outline, Tone.orange),
];

/// The home page after a citizen logs in: Register Complaint and Track Complaint, the services, the citizen's
/// numbers, how it works, and the citizen's complaints with the "is it fixed?" question. It updates every 5 seconds.
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.profile});

  final Map<String, dynamic> profile;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final _scroll = ScrollController();
  final _servicesKey = GlobalKey();
  final _howKey = GlobalKey();

  List<Map<String, dynamic>> _items = <Map<String, dynamic>>[];
  final Map<String, Map<String, dynamic>> _details = <String, Map<String, dynamic>>{};
  final Map<String, String> _codes = <String, String>{};
  final Map<String, String> _codeMinutes = <String, String>{};
  final Map<String, TextEditingController> _comments = <String, TextEditingController>{};
  final Map<String, TextEditingController> _codeInputs = <String, TextEditingController>{};

  bool _loaded = false;
  bool _offline = false;
  bool _loading = false;
  int _gen = 0; // goes up with every load, so an older answer that arrives late is ignored
  String? _error;
  Timer? _timer;

  String get _mobile => widget.profile['mobile']?.toString() ?? '';

  @override
  void initState() {
    super.initState();
    _load(force: true);
    _timer = Timer.periodic(const Duration(seconds: 5), (_) => _load());
  }

  @override
  void dispose() {
    _timer?.cancel();
    _scroll.dispose();
    for (final controller in _comments.values) {
      controller.dispose();
    }
    for (final controller in _codeInputs.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _load({bool force = false}) async {
    if (_loading && !force) return;
    final gen = ++_gen;
    _loading = true;
    try {
      final items = await api.citizenComplaints();
      final details = <String, Map<String, dynamic>>{};
      // The full view is needed to confirm a fix, and to show a code a worker asked for.
      for (final item in items) {
        if (item['status'] != 'awaiting_confirmation' && item['work_status'] != 'allotted') continue;
        final id = item['id']?.toString() ?? '';
        try {
          details[id] = await api.track(id, _mobile);
        } on ApiException {
          // Shown without the code step.
        }
      }
      if (!mounted || gen != _gen) return;
      setState(() {
        _items = items;
        _details
          ..clear()
          ..addAll(details);
        _loaded = true;
        _offline = false;
      });
    } on ApiException catch (error) {
      if (!mounted || gen != _gen) return;
      if (error.status == 401) {
        // Only when this screen is in front; Register or Track above it sends the citizen back itself.
        if (ModalRoute.of(context)?.isCurrent ?? true) {
          returnToLogin(context, message: 'Your login has ended. Log in again.');
        }
        return;
      }
      setState(() => _offline = true);
    } finally {
      if (gen == _gen) _loading = false;
    }
  }

  Future<void> _confirm(String id, bool fixed) async {
    setState(() => _error = null);
    try {
      final view = await api.confirm(id, _mobile, fixed: fixed, comment: _comments[id]?.text ?? '');
      if (!mounted) return;
      final code = view['demo_code'];
      if (fixed && code != null) {
        _codes[id] = code.toString();
        _codeMinutes[id] = view['demo_code_minutes']?.toString() ?? '10';
      }
      _comments[id]?.clear();
      await _load(force: true);
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
  }

  Future<void> _closeWithCode(String id) async {
    setState(() => _error = null);
    try {
      await api.confirmCode(id, _mobile, _codeInputs[id]?.text.trim() ?? '');
      if (!mounted) return;
      _codes.remove(id);
      _codeInputs[id]?.clear();
      await _load(force: true);
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    }
  }

  Future<void> _logout() async {
    try {
      await api.logout();
    } catch (_) {
      // The session ends on this device either way.
    }
    if (mounted) returnToLogin(context);
  }

  Future<void> _openRegister(String? service) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => RegisterComplaintScreen(profile: widget.profile, service: service)),
    );
    _load(force: true);
  }

  Future<void> _openTrack([String? id]) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => TrackComplaintScreen(profile: widget.profile, initialId: id)),
    );
    _load(force: true);
  }

  void _scrollToTop() {
    if (_scroll.hasClients) {
      _scroll.animateTo(0, duration: const Duration(milliseconds: 400), curve: Curves.easeOut);
    }
  }

  void _scrollTo(GlobalKey key) {
    final target = key.currentContext;
    if (target != null) {
      Scrollable.ensureVisible(target, duration: const Duration(milliseconds: 400), curve: Curves.easeOut);
    }
  }

  int _count(String status) => _items.where((item) => item['status'] == status).length;

  @override
  Widget build(BuildContext context) {
    final name = widget.profile['name']?.toString() ?? '';
    final first = name.trim().split(RegExp(r'\s+')).first;
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          controller: _scroll,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              PortalTopBar(
                onBrandTap: _scrollToTop,
                links: [
                  NavLink('Home', _scrollToTop, selected: true),
                  NavLink('Register Complaint', () => _openRegister(null)),
                  NavLink('Track Complaint', _openTrack),
                  NavLink('Services', () => _scrollTo(_servicesKey)),
                  NavLink('How It Works', () => _scrollTo(_howKey)),
                ],
                trailing: [
                  AccountButton(name: name, details: citizenDetails(widget.profile), onLogout: _logout),
                ],
              ),
              HeroBanner(
                showDrop: true,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      first.isEmpty ? 'Welcome' : 'Welcome, $first',
                      style: const TextStyle(color: Palette.sky, fontSize: 15, fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 8),
                    const HeroHeadline(),
                    const HeroLead(
                      'Report water and sewer problems, follow their progress, and confirm when they are fixed. '
                      'Your voice matters.',
                    ),
                    Padding(
                      padding: const EdgeInsets.only(top: 24),
                      child: Wrap(
                        spacing: 14,
                        runSpacing: 12,
                        children: [
                          PortalButton(
                            label: 'Register Complaint',
                            icon: Icons.edit_note,
                            trailingIcon: Icons.arrow_forward,
                            kind: ButtonKind.light,
                            onPressed: () => _openRegister(null),
                          ),
                          PortalButton(
                            label: 'Track Complaint',
                            icon: Icons.search,
                            trailingIcon: Icons.arrow_forward,
                            kind: ButtonKind.onBlue,
                            onPressed: _openTrack,
                          ),
                        ],
                      ),
                    ),
                    const FeatureChips(),
                  ],
                ),
              ),
              PageWidth(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Padding(
                      key: _servicesKey,
                      padding: const EdgeInsets.only(top: 26, bottom: 14),
                      child: SectionHead(
                        title: 'Common Services',
                        subtitle: 'Report problems with water and sewer services.',
                        trailing: TextButton(
                          onPressed: () => _openRegister(null),
                          child: const Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text('Register a complaint', style: TextStyle(fontWeight: FontWeight.w600)),
                              SizedBox(width: 6),
                              Icon(Icons.arrow_forward, size: 16),
                            ],
                          ),
                        ),
                      ),
                    ),
                    _servicesGrid(),
                    const SizedBox(height: 26),
                    NumbersStrip(
                      title: 'Your Complaints in Numbers',
                      subtitle: 'From your account. Updates on its own.',
                      stats: [
                        StatData(Icons.description_outlined, Tone.blue, _items.length, 'Registered'),
                        StatData(Icons.schedule, Tone.orange, _count('open'), 'In progress'),
                        StatData(Icons.warning_amber_rounded, Tone.yellow, _count('awaiting_confirmation'), 'Waiting for you'),
                        StatData(Icons.check_circle_outline, Tone.green, _count('closed'), 'Resolved'),
                      ],
                    ),
                    Padding(
                      key: _howKey,
                      padding: const EdgeInsets.only(top: 26, bottom: 30),
                      child: _howItWorks(),
                    ),
                    _mine(),
                    const SizedBox(height: 12),
                  ],
                ),
              ),
              const PortalFooter(),
            ],
          ),
        ),
      ),
    );
  }

  Widget _servicesGrid() {
    return LayoutBuilder(
      builder: (context, constraints) {
        final available = constraints.maxWidth;
        final columns = available >= 1000 ? 6 : (available >= 560 ? 3 : 2);
        const gap = 14.0;
        final cardWidth = (available - gap * (columns - 1)) / columns - 0.5;
        return Wrap(
          spacing: gap,
          runSpacing: gap,
          children: [
            for (final service in _services)
              SizedBox(width: cardWidth, child: _serviceCard(service)),
          ],
        );
      },
    );
  }

  Widget _serviceCard(_Service service) {
    return Container(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        boxShadow: const [BoxShadow(color: Color(0x12023668), blurRadius: 10, offset: Offset(0, 2))],
      ),
      child: Material(
        color: Palette.white,
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: () => _openRegister(service.key),
          child: Container(
            constraints: const BoxConstraints(minHeight: 190),
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: Palette.line),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(color: service.tone.background, shape: BoxShape.circle),
                  child: Icon(service.icon, size: 22, color: service.tone.foreground),
                ),
                const SizedBox(height: 10),
                Text(
                  service.title,
                  style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700, color: Palette.navy),
                ),
                const SizedBox(height: 6),
                Text(service.text, style: const TextStyle(fontSize: TextSizes.small, color: Palette.muted)),
                const SizedBox(height: 12),
                const Icon(Icons.arrow_forward, size: 18, color: Palette.navy),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _howItWorks() {
    const intro = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          'How It Works',
          style: TextStyle(fontSize: TextSizes.sectionTitle, fontWeight: FontWeight.w800, color: Palette.navy),
        ),
        SizedBox(height: 4),
        Text(
          'From complaint to resolution, in four simple steps.',
          style: TextStyle(fontSize: TextSizes.label, color: Palette.muted),
        ),
      ],
    );
    final steps = LayoutBuilder(
      builder: (context, constraints) {
        final available = constraints.maxWidth;
        final columns = available >= 820 ? 4 : (available >= 520 ? 2 : 1);
        const gap = 18.0;
        final width = (available - gap * (columns - 1)) / columns - 0.5;
        return Wrap(
          spacing: gap,
          runSpacing: gap,
          children: [
            for (final step in _steps) SizedBox(width: width, child: _stepTile(step)),
          ],
        );
      },
    );
    if (MediaQuery.sizeOf(context).width >= 1100) {
      return Row(
        children: [
          const SizedBox(width: 240, child: intro),
          const SizedBox(width: 24),
          Expanded(child: steps),
        ],
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [intro, const SizedBox(height: 16), steps],
    );
  }

  Widget _stepTile(_Step step) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Container(
          width: 46,
          height: 46,
          decoration: BoxDecoration(color: step.tone.background, shape: BoxShape.circle),
          child: Icon(step.icon, size: 22, color: step.tone.foreground),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(step.title,
                  style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w700, color: Palette.navy)),
              Text(step.text, style: const TextStyle(fontSize: TextSizes.small, color: Palette.muted)),
            ],
          ),
        ),
      ],
    );
  }

  Widget _mine() {
    final error = _error;
    final rows = <Widget>[];
    if (!_loaded) {
      rows.add(const Padding(
        padding: EdgeInsets.all(16),
        child: Center(child: CircularProgressIndicator()),
      ));
    } else if (_items.isEmpty) {
      rows.add(Padding(
        padding: const EdgeInsets.only(top: 12),
        child: Wrap(
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            const Text('You have not registered a complaint yet.',
                style: TextStyle(fontSize: TextSizes.label, color: Palette.muted)),
            TextButton(onPressed: () => _openRegister(null), child: const Text('Register a complaint')),
          ],
        ),
      ));
    } else {
      for (final item in _items) {
        rows.add(_complaintRow(item));
      }
    }
    return Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SectionHead(
            title: 'Your Complaints',
            subtitle: 'A green Resolved shows when a complaint is resolved. Tap Track to see every step.',
            trailing: LiveIndicator(text: _offline ? 'Cannot reach the server' : 'Live', paused: _offline),
          ),
          if (error != null) ErrorText(error),
          const SizedBox(height: 10),
          ...rows,
        ],
      ),
    );
  }

  Widget _complaintRow(Map<String, dynamic> item) {
    String text(String key) => item[key]?.toString() ?? '';
    final id = text('id');
    final status = text('status');
    final landmark = text('landmark');
    final worker = item['worker'];
    final code = _details[id]?['completion_code']?.toString() ?? '';
    final meta = <String>[
      if (text('problem_address').isNotEmpty)
        'At: ${text('problem_address')}${landmark.isEmpty ? '' : ' ($landmark)'}',
      if (worker is Map)
        'Worker: ${worker['name'] ?? ''} (${worker['department'] ?? ''})'
      else ...[
        'With: ${text('current_office')}',
        'Officer: ${text('assigned_to')}',
      ],
      if (text('zone').isNotEmpty) '${text('zone')}, ${text('ward')}',
      if (status == 'open') 'Time limit: ${formatWhen(item['deadline']?.toString())}',
    ].join('  ·  ');
    return Container(
      key: ValueKey<String>(id),
      padding: const EdgeInsets.symmetric(vertical: 14),
      decoration: const BoxDecoration(border: Border(top: BorderSide(color: Palette.line))),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // The ID, what it is and a Track link; the status (a green Resolved when resolved) at the right side.
          JobTop(
            id: id,
            label: '${text('complaint_label')} (${text('field')})',
            pills: [
              if (item['overdue'] == true) Pill.overdue(),
              TextButton(
                onPressed: () => _openTrack(id),
                style: TextButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 6)),
                child: const Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text('Track', style: TextStyle(fontWeight: FontWeight.w600)),
                    SizedBox(width: 4),
                    Icon(Icons.arrow_forward, size: 16),
                  ],
                ),
              ),
            ],
            side: StatusPill.forCitizen(item),
          ),
          const SizedBox(height: 4),
          Text(meta, style: const TextStyle(fontSize: 13.5, color: Palette.muted)),
          if (code.isNotEmpty) CodeForWorkerBox(code: code, minutes: _details[id]?['completion_code_minutes']?.toString()),
          if (status == 'awaiting_confirmation') _confirmBox(id),
        ],
      ),
    );
  }

  Widget _confirmBox(String id) {
    final awaitingCode = _details[id]?['awaiting_code'] == true;
    final shownCode = _codes[id];
    const message = TextStyle(fontSize: TextSizes.label, color: Palette.warn);
    final children = <Widget>[];
    if (awaitingCode) {
      final input = _codeInputs.putIfAbsent(id, () => TextEditingController());
      children
        ..add(Text(
          shownCode != null
              ? 'Enter this code to close the complaint: $shownCode. It is shown here instead of an SMS '
                  'and lasts ${_codeMinutes[id] ?? '10'} minutes.'
              : 'Enter the code sent to your mobile by SMS to close the complaint, or ask for a new one.',
          style: message,
        ))
        ..add(const SizedBox(height: 8))
        ..add(Wrap(
          spacing: 10,
          runSpacing: 10,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            SizedBox(
              width: 200,
              child: TextField(
                controller: input,
                keyboardType: TextInputType.number,
                inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(6)],
                decoration: const InputDecoration(hintText: '6-digit code', fillColor: Palette.white),
              ),
            ),
            PortalButton(label: 'Close the complaint', small: true, onPressed: () => _closeWithCode(id)),
            if (shownCode == null)
              PortalButton(
                label: 'Show a new code',
                small: true,
                kind: ButtonKind.outline,
                onPressed: () => _confirm(id, true),
              ),
          ],
        ));
    } else {
      final comment = _comments.putIfAbsent(id, () => TextEditingController());
      children
        ..add(const Text('An officer has marked this complaint resolved. Is the problem really fixed?', style: message))
        ..add(const SizedBox(height: 8))
        ..add(Wrap(
          spacing: 10,
          runSpacing: 10,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            SizedBox(
              width: 220,
              child: TextField(
                controller: comment,
                decoration: const InputDecoration(hintText: 'Comment (optional)', fillColor: Palette.white),
              ),
            ),
            PortalButton(label: 'Yes, it is fixed', small: true, onPressed: () => _confirm(id, true)),
            PortalButton(
              label: 'No, still not fixed',
              small: true,
              kind: ButtonKind.danger,
              onPressed: () => _confirm(id, false),
            ),
          ],
        ));
    }
    return Container(
      margin: const EdgeInsets.only(top: 10),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(color: Palette.warnBg, borderRadius: BorderRadius.circular(8)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: children),
    );
  }
}
