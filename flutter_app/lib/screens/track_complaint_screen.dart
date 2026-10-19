import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/api_client.dart';
import '../theme.dart';
import '../widgets/account_button.dart';
import '../widgets/board.dart';
import '../widgets/common.dart';
import '../widgets/router_panels.dart';
import 'login_screen.dart';
import 'register_complaint_screen.dart';

class _StepInfo {
  const _StepInfo(this.icon, this.title, this.subtitle);

  final IconData icon;
  final String title;
  final String subtitle;
}

/// Track Complaint: a search bar for the complaint ID at the top (or pick one of your own), where the complaint is,
/// who is working on it, a green Resolved when it is resolved, and its history. It is checked again every 5 seconds.
class TrackComplaintScreen extends StatefulWidget {
  const TrackComplaintScreen({super.key, required this.profile, this.initialId});

  final Map<String, dynamic> profile;

  /// The complaint to show first. Null: the citizen's newest complaint.
  final String? initialId;

  @override
  State<TrackComplaintScreen> createState() => _TrackComplaintScreenState();
}

class _TrackComplaintScreenState extends State<TrackComplaintScreen> {
  final _id = TextEditingController();
  final _comment = TextEditingController();
  final _code = TextEditingController();

  List<Map<String, dynamic>> _mine = <Map<String, dynamic>>[];
  Map<String, dynamic>? _view;
  String? _error;
  String? _confirmError;
  bool _loadedMine = false;
  bool _busy = false;
  bool _offline = false;
  bool _refreshing = false;
  int _seq = 0; // goes up whenever the shown complaint changes, so an older refresh does not overwrite it
  final Map<String, String> _codes = <String, String>{};
  final Map<String, String> _codeMinutes = <String, String>{};
  Timer? _timer;

  String get _mobile => widget.profile['mobile']?.toString() ?? '';

  @override
  void initState() {
    super.initState();
    _start();
    _timer = Timer.periodic(const Duration(seconds: 5), (_) => _refresh());
  }

  @override
  void dispose() {
    _timer?.cancel();
    _id.dispose();
    _comment.dispose();
    _code.dispose();
    super.dispose();
  }

  void _loginEnded() => returnToLogin(context, message: 'Your login has ended. Log in again.');

  Future<void> _start() async {
    final ok = await _loadMine();
    if (!ok || !mounted) return;
    final asked = widget.initialId;
    if (asked != null && asked.isNotEmpty) {
      await _track(asked);
    } else if (_mine.isNotEmpty) {
      await _track(_mine.first['id']?.toString() ?? '');
    }
  }

  /// Loads the citizen's complaints for the buttons. False when the login has ended.
  Future<bool> _loadMine() async {
    try {
      final items = await api.citizenComplaints();
      if (!mounted) return false;
      setState(() {
        _mine = items;
        _loadedMine = true;
      });
      return true;
    } on ApiException catch (error) {
      if (!mounted) return false;
      if (error.status == 401) {
        _loginEnded();
        return false;
      }
      setState(() => _loadedMine = true);
      return true;
    }
  }

  Future<void> _track(String id) async {
    final wanted = id.trim();
    if (wanted.isEmpty) {
      setState(() => _error = 'Enter a complaint ID.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
      _confirmError = null;
    });
    try {
      final view = await api.track(wanted, _mobile);
      if (!mounted) return;
      setState(() {
        _seq++;
        _view = view;
        _id.text = view['id']?.toString() ?? wanted;
        _offline = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      if (error.status == 401) {
        _loginEnded();
        return;
      }
      setState(() {
        _view = null;
        _error = error.message;
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  // Every 5 seconds: so an officer's action shows up here by itself.
  Future<void> _refresh() async {
    final current = _view?['id']?.toString();
    if (current == null || _busy || _refreshing) return;
    _refreshing = true;
    final seq = _seq;
    try {
      final view = await api.track(current, _mobile);
      final items = await api.citizenComplaints();
      if (!mounted || seq != _seq) return;
      setState(() {
        _view = view;
        _mine = items;
        _offline = false;
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      if (error.status == 401) {
        _loginEnded();
        return;
      }
      setState(() => _offline = true);
    } finally {
      _refreshing = false;
    }
  }

  Future<void> _confirm(bool fixed) async {
    final id = _view?['id']?.toString();
    if (id == null) return;
    setState(() => _confirmError = null);
    try {
      final view = await api.confirm(id, _mobile, fixed: fixed, comment: _comment.text);
      if (!mounted) return;
      final code = view['demo_code'];
      setState(() {
        if (fixed && code != null) {
          _codes[id] = code.toString();
          _codeMinutes[id] = view['demo_code_minutes']?.toString() ?? '10';
        }
        _seq++;
        _view = view;
        _comment.clear();
      });
      _loadMine();
    } on ApiException catch (error) {
      if (mounted) setState(() => _confirmError = error.message);
    }
  }

  Future<void> _closeWithCode() async {
    final id = _view?['id']?.toString();
    if (id == null) return;
    setState(() => _confirmError = null);
    try {
      final view = await api.confirmCode(id, _mobile, _code.text.trim());
      if (!mounted) return;
      setState(() {
        _codes.remove(id);
        _code.clear();
        _seq++;
        _view = view;
      });
      _loadMine();
    } on ApiException catch (error) {
      if (mounted) setState(() => _confirmError = error.message);
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

  void _goHome() => Navigator.of(context).popUntil((route) => route.isFirst);

  @override
  Widget build(BuildContext context) {
    final view = _view;
    final error = _error;
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
                  NavLink('Register Complaint', () {
                    Navigator.of(context).pushReplacement(
                      MaterialPageRoute<void>(builder: (_) => RegisterComplaintScreen(profile: widget.profile)),
                    );
                  }),
                  NavLink('Track Complaint', () {}, selected: true),
                ],
                trailing: [
                  AccountButton(
                    name: widget.profile['name']?.toString() ?? '',
                    details: citizenDetails(widget.profile),
                    onLogout: _logout,
                  ),
                ],
              ),
              HeroBanner(
                compact: true,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const HeroHeadline(compact: true, line1: '', before: 'Track Your ', sky: 'Complaint'),
                    const HeroLead('Enter your complaint ID to see where it is, who is working on it, and its time limit.'),
                    _search(),
                    if (error != null)
                      Container(
                        margin: const EdgeInsets.only(top: 10),
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                        decoration: BoxDecoration(
                          color: const Color(0xD9B3261E),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          error,
                          style: const TextStyle(color: Palette.white, fontWeight: FontWeight.w600, fontSize: 14),
                        ),
                      ),
                  ],
                ),
              ),
              PageWidth(
                child: FormCard(
                  icon: Icons.search,
                  title: 'Track Complaint',
                  subtitle: 'Search above, or choose one of your complaints below.',
                  headTrailing: LiveIndicator(text: _offline ? 'Cannot reach the server' : 'Live', paused: _offline),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (_mine.isNotEmpty) ...[
                        _picks(),
                        const SizedBox(height: 14),
                        const Divider(color: Palette.line, height: 1),
                        const SizedBox(height: 18),
                      ],
                      if (view != null)
                        _result(view)
                      else if (_loadedMine && _mine.isEmpty)
                        Wrap(
                          crossAxisAlignment: WrapCrossAlignment.center,
                          children: [
                            const Text('You have not registered a complaint yet.',
                                style: TextStyle(fontSize: TextSizes.label, color: Palette.muted)),
                            TextButton(
                              onPressed: () => Navigator.of(context).pushReplacement(
                                MaterialPageRoute<void>(
                                  builder: (_) => RegisterComplaintScreen(profile: widget.profile),
                                ),
                              ),
                              child: const Text('Register a complaint'),
                            ),
                          ],
                        )
                      else if (!_loadedMine || _busy)
                        const Padding(
                          padding: EdgeInsets.all(16),
                          child: Center(child: CircularProgressIndicator()),
                        ),
                    ],
                  ),
                ),
              ),
              const PortalFooter(),
            ],
          ),
        ),
      ),
    );
  }

  /// The white search bar in the blue banner: the complaint ID and a Track button.
  Widget _search() {
    final phone = isPhone(context);
    return Padding(
      padding: const EdgeInsets.only(top: 22),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 760),
        child: Container(
          padding: EdgeInsets.fromLTRB(phone ? 10 : 16, 7, 7, 7),
          decoration: BoxDecoration(
            color: Palette.white,
            borderRadius: BorderRadius.circular(12),
            boxShadow: const [BoxShadow(color: Color(0x47021E46), blurRadius: 30, offset: Offset(0, 10))],
          ),
          child: Row(
            children: [
              const Icon(Icons.search, color: Palette.navy, size: 22),
              const SizedBox(width: 8),
              Expanded(
                child: TextField(
                  controller: _id,
                  textCapitalization: TextCapitalization.characters,
                  inputFormatters: [LengthLimitingTextInputFormatter(30)],
                  style: TextStyle(fontSize: phone ? 15 : 17, color: Palette.text),
                  decoration: InputDecoration(
                    hintText: phone ? 'Enter your complaint ID' : 'Enter your complaint ID, for example CMP-20261018-1234',
                    filled: false,
                    border: InputBorder.none,
                    enabledBorder: InputBorder.none,
                    focusedBorder: InputBorder.none,
                    isDense: true,
                    contentPadding: const EdgeInsets.symmetric(vertical: 12),
                  ),
                  onSubmitted: _track,
                ),
              ),
              const SizedBox(width: 8),
              SizedBox(
                height: 46,
                child: PortalButton(label: 'Track', busy: _busy, onPressed: () => _track(_id.text)),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _picks() {
    final currentId = _view?['id']?.toString();
    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Your complaints:', style: TextStyle(fontSize: TextSizes.small, color: Palette.muted)),
          const SizedBox(height: 6),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final item in _mine)
                InkWell(
                  borderRadius: BorderRadius.circular(999),
                  onTap: () => _track(item['id']?.toString() ?? ''),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      color: item['id']?.toString() == currentId ? Palette.sectionBg : Palette.white,
                      borderRadius: BorderRadius.circular(999),
                      border: Border.all(
                        color: item['id']?.toString() == currentId ? Palette.primary : Palette.line,
                        width: item['id']?.toString() == currentId ? 2 : 1,
                      ),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Flexible(
                          child: Text(
                            item['id']?.toString() ?? '',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600, color: Palette.navy),
                          ),
                        ),
                        const SizedBox(width: 8),
                        StatusPill.forCitizen(item, short: true),
                      ],
                    ),
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _result(Map<String, dynamic> view) {
    String text(String key) => view[key]?.toString() ?? '';
    final status = text('status');
    final events = view['events'];
    final confirmError = _confirmError;
    final worker = view['worker'];
    final code = text('completion_code');
    final rows = <MapEntry<String, String>>[
      MapEntry('Type', text('complaint_label')),
      MapEntry('Field', text('field')),
      MapEntry('Address of the problem', text('problem_address').isEmpty ? 'Not given' : text('problem_address')),
      MapEntry('Landmark', text('landmark').isEmpty ? 'None' : text('landmark')),
      MapEntry('Zone and ward', text('zone').isEmpty ? 'Not recorded' : '${text('zone')}, ${text('ward')}'),
      MapEntry(
        'Worker',
        worker is Map
            ? '${worker['name'] ?? ''} (${worker['department'] ?? ''}), ${worker['mobile'] ?? ''}'
            : 'Not allotted yet',
      ),
      MapEntry('Office in charge', text('current_office')),
      MapEntry('Officer', text('assigned_to')),
      MapEntry('Time limit', status == 'open' ? formatWhen(view['deadline']?.toString()) : 'Not running'),
      MapEntry('Registered on', formatWhen(view['created_at']?.toString(), empty: '-')),
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            color: Palette.sectionBg,
            border: Border.all(color: Palette.cardEdge),
            borderRadius: BorderRadius.circular(10),
          ),
          child: JobTop(
            id: text('id'),
            label: '',
            pills: [
              Text(text('status_text'), style: const TextStyle(fontSize: TextSizes.label, color: Palette.labelText)),
            ],
            side: StatusPill.forCitizen(view),
          ),
        ),
        const SizedBox(height: 22),
        _stepper(view),
        const SizedBox(height: 10),
        TwoColumns(
          left: [
            const _Heading('Details'),
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
            const SizedBox(height: 6),
            const _Heading('Your complaint'),
            Container(
              padding: const EdgeInsets.all(12),
              margin: const EdgeInsets.only(bottom: 14),
              decoration: BoxDecoration(
                color: Palette.page,
                border: Border.all(color: Palette.line),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(text('complaint_text'), style: const TextStyle(fontSize: TextSizes.body, height: 1.5)),
            ),
          ],
          right: [
            if (code.isNotEmpty && code != 'null')
              CodeForWorkerBox(code: code, minutes: view['completion_code_minutes']?.toString()),
            if (view['can_confirm'] == true) _confirmBox(view),
            if (confirmError != null) ErrorText(confirmError),
            const SizedBox(height: 6),
            // The router's timeline for this complaint, and the message it wrote when the complaint was registered.
            if (view['router_progress'] is Map) ...[
              const _Heading('Time limits from the router'),
              RouterProgress(progress: view['router_progress']),
              if (text('router_message').isNotEmpty)
                ExpansionTile(
                  tilePadding: EdgeInsets.zero,
                  title: const Text(
                    'Message from the complaint router',
                    style: TextStyle(fontSize: TextSizes.label, fontWeight: FontWeight.w700, color: Palette.primary),
                  ),
                  children: [RouterMessage(message: text('router_message'))],
                ),
              const SizedBox(height: 8),
            ],
            const _Heading('History'),
            if (events is List) _history(events),
          ],
        ),
      ],
    );
  }

  Widget _stepper(Map<String, dynamic> view) {
    // Registered -> Allotted -> Work in progress -> Resolved, as on the web page.
    final status = view['status']?.toString() ?? '';
    var position = 1;
    if (status == 'closed') {
      position = 4;
    } else if (status == 'awaiting_confirmation') {
      position = 3;
    } else if (view['work_status'] == 'allotted') {
      position = 2;
    }
    final worker = view['worker'];
    final workerText = worker is Map ? '${worker['name'] ?? ''} (${worker['department'] ?? ''})' : '';
    final steps = <_StepInfo>[
      _StepInfo(Icons.edit_note, 'Registered', formatWhen(view['created_at']?.toString(), empty: '')),
      _StepInfo(
        Icons.engineering_outlined,
        'Allotted',
        workerText.isNotEmpty ? workerText : (position > 1 ? 'Done' : 'Waiting for a worker'),
      ),
      _StepInfo(
        Icons.construction_outlined,
        'Work in progress',
        position == 2 ? 'The worker is on it' : (position > 2 ? 'Done' : 'Not yet'),
      ),
      _StepInfo(
        Icons.check_circle_outline,
        'Resolved',
        status == 'closed' ? 'Problem fixed' : (position == 3 ? 'Confirm the fix below' : 'Not yet'),
      ),
    ];

    Widget dot(int i) {
      final done = i < position;
      final current = i == position;
      return Container(
        width: 40,
        height: 40,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: done ? Palette.primary : Palette.white,
          border: Border.all(color: done || current ? Palette.primary : Palette.line, width: 3),
          boxShadow: current ? const [BoxShadow(color: Color(0x24066DD1), spreadRadius: 6)] : null,
        ),
        child: Icon(
          done ? Icons.check : steps[i].icon,
          size: 18,
          color: done ? Palette.white : (current ? Palette.primary : Palette.muted),
        ),
      );
    }

    Widget words(int i, {required bool centred}) {
      final align = centred ? TextAlign.center : TextAlign.start;
      return Column(
        crossAxisAlignment: centred ? CrossAxisAlignment.center : CrossAxisAlignment.start,
        children: [
          Text(steps[i].title,
              textAlign: align,
              style: const TextStyle(fontSize: TextSizes.label, fontWeight: FontWeight.w700, color: Palette.navy)),
          Text(steps[i].subtitle,
              textAlign: align, style: const TextStyle(fontSize: TextSizes.tiny, color: Palette.muted)),
        ],
      );
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth < 480) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (var i = 0; i < steps.length; i++)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: Row(
                    children: [dot(i), const SizedBox(width: 12), Expanded(child: words(i, centred: false))],
                  ),
                ),
            ],
          );
        }
        final stepWidth = math.min(150.0, (constraints.maxWidth - 60) / steps.length);
        return Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (var i = 0; i < steps.length; i++) ...[
              if (i > 0)
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.only(top: 18.5),
                    child: Container(height: 3, color: i <= position ? Palette.primary : Palette.line),
                  ),
                ),
              SizedBox(
                width: stepWidth,
                child: Column(children: [dot(i), const SizedBox(height: 8), words(i, centred: true)]),
              ),
            ],
          ],
        );
      },
    );
  }

  Widget _confirmBox(Map<String, dynamic> view) {
    final id = view['id']?.toString() ?? '';
    final shownCode = _codes[id];
    const message = TextStyle(fontSize: TextSizes.label, color: Palette.warn);
    final children = <Widget>[];
    if (view['awaiting_code'] == true) {
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
                controller: _code,
                keyboardType: TextInputType.number,
                inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(6)],
                decoration: const InputDecoration(hintText: '6-digit code', fillColor: Palette.white),
              ),
            ),
            PortalButton(label: 'Close the complaint', small: true, onPressed: _closeWithCode),
            if (shownCode == null)
              PortalButton(
                label: 'Show a new code',
                small: true,
                kind: ButtonKind.outline,
                onPressed: () => _confirm(true),
              ),
          ],
        ));
    } else {
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
                controller: _comment,
                decoration: const InputDecoration(hintText: 'Comment (optional)', fillColor: Palette.white),
              ),
            ),
            PortalButton(label: 'Yes, it is fixed', small: true, onPressed: () => _confirm(true)),
            PortalButton(
              label: 'No, still not fixed',
              small: true,
              kind: ButtonKind.danger,
              onPressed: () => _confirm(false),
            ),
          ],
        ));
    }
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(color: Palette.warnBg, borderRadius: BorderRadius.circular(8)),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: children),
    );
  }

  Widget _history(List<dynamic> events) {
    final newestFirst = events.reversed.whereType<Map>().toList();
    return Container(
      margin: const EdgeInsets.only(left: 6),
      padding: const EdgeInsets.only(left: 18),
      decoration: const BoxDecoration(border: Border(left: BorderSide(color: Palette.line, width: 2))),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final event in newestFirst)
            Padding(
              padding: const EdgeInsets.only(bottom: 14),
              child: Stack(
                clipBehavior: Clip.none,
                children: [
                  Positioned(
                    left: -25,
                    top: 3,
                    child: Container(
                      width: 12,
                      height: 12,
                      decoration: BoxDecoration(
                        color: Palette.white,
                        shape: BoxShape.circle,
                        border: Border.all(color: Palette.primaryBright, width: 3),
                      ),
                    ),
                  ),
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(formatWhen(event['at']?.toString()),
                          style: const TextStyle(fontSize: TextSizes.tiny, color: Palette.muted)),
                      Text(event['message']?.toString() ?? '',
                          style: const TextStyle(fontSize: TextSizes.label, color: Palette.text)),
                    ],
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _Heading extends StatelessWidget {
  const _Heading(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(text, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700, color: Palette.navy)),
    );
  }
}
