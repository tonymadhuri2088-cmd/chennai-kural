import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/api_client.dart';
import '../theme.dart';
import '../widgets/account_button.dart';
import '../widgets/board.dart';
import '../widgets/common.dart';
import 'login_screen.dart';

/// The worker's details for the account icon.
List<MapEntry<String, String>> workerDetails(Map<String, dynamic> worker) {
  String text(String key) => worker[key]?.toString() ?? '';
  return [
    MapEntry('Name', text('name')),
    MapEntry('Mobile', text('mobile')),
    MapEntry('Department', text('department')),
    MapEntry('Address', text('address')),
    MapEntry('Zone', text('zone')),
    MapEntry('Ward', text('ward')),
  ];
}

/// The two lists on the worker's screen.
enum WorkerView { available, mine }

/// The worker dashboard: "Complaints registered" (open complaints nobody has taken) and "Allotted tasks"
/// (the complaints this worker accepted). It checks for changes every 5 seconds.
class WorkerHomeScreen extends StatefulWidget {
  const WorkerHomeScreen({super.key, required this.worker});

  final Map<String, dynamic> worker;

  @override
  State<WorkerHomeScreen> createState() => _WorkerHomeScreenState();
}

class _WorkerHomeScreenState extends State<WorkerHomeScreen> {
  WorkerView _view = WorkerView.available;
  List<Map<String, dynamic>> _available = <Map<String, dynamic>>[];
  List<Map<String, dynamic>> _mine = <Map<String, dynamic>>[];
  Set<String>? _seen; // complaint IDs already shown, to mark new arrivals
  final Set<String> _fresh = <String>{};
  final Set<String> _detailsOpen = <String>{};
  final Set<String> _busyIds = <String>{};
  final Map<String, Map<String, dynamic>> _codeSent = <String, Map<String, dynamic>>{};
  final Map<String, TextEditingController> _codeInputs = <String, TextEditingController>{};
  final Map<String, String> _codeErrors = <String, String>{};

  bool _loaded = false;
  bool _offline = false;
  bool _loading = false;
  int _gen = 0; // goes up with every load, so an older answer that arrives late is ignored
  DateTime? _updated;
  String? _error;
  Timer? _timer;

  String _text(String key) => widget.worker[key]?.toString() ?? '';

  @override
  void initState() {
    super.initState();
    _load(force: true);
    _timer = Timer.periodic(const Duration(seconds: 5), (_) => _load());
  }

  @override
  void dispose() {
    _timer?.cancel();
    for (final controller in _codeInputs.values) {
      controller.dispose();
    }
    super.dispose();
  }

  void _loginEnded() {
    returnToLogin(context, message: 'Log in as a worker to continue.', isError: true, workerTab: true);
  }

  Future<void> _load({bool force = false}) async {
    if (_loading && !force) return;
    final gen = ++_gen;
    _loading = true;
    try {
      final board = await api.workerBoard();
      if (!mounted || gen != _gen) return;
      final available = board['available'] ?? <Map<String, dynamic>>[];
      final ids = available.map((item) => item['id']?.toString() ?? '').toSet();
      final seen = _seen;
      final arrived = seen == null ? <String>{} : ids.difference(seen);
      setState(() {
        _fresh
          ..addAll(arrived)
          ..removeWhere((id) => !ids.contains(id));
        _seen = ids;
        _available = available;
        _mine = board['mine'] ?? <Map<String, dynamic>>[];
        _loaded = true;
        _offline = false;
        _updated = DateTime.now();
      });
      if (arrived.isNotEmpty) showToast(context, 'A new complaint was registered.');
    } on ApiException catch (error) {
      if (!mounted || gen != _gen) return;
      if (error.status == 401) {
        _loginEnded();
        return;
      }
      setState(() => _offline = true);
    } finally {
      if (gen == _gen) _loading = false;
    }
  }

  Future<void> _accept(String id) async {
    setState(() {
      _busyIds.add(id);
      _error = null;
    });
    try {
      await api.workerAccept(id);
      if (!mounted) return;
      _fresh.remove(id);
      showToast(
        context,
        '$id is now in your allotted tasks. The citizen sees "Allotted" and "Work in progress".',
        actionLabel: 'Open allotted tasks',
        onAction: () {
          if (mounted) setState(() => _view = WorkerView.mine);
        },
      );
    } on ApiException catch (error) {
      if (!mounted) return;
      if (error.status == 401) {
        _loginEnded();
        return;
      }
      setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busyIds.remove(id));
    }
    await _load(force: true);
  }

  Future<void> _requestCode(String id) async {
    setState(() {
      _busyIds.add(id);
      _error = null;
    });
    try {
      final sent = await api.workerRequestCompletion(id);
      if (!mounted) return;
      setState(() {
        _codeSent[id] = sent;
        _codeErrors.remove(id);
        _codeInputs[id]?.clear();
      });
    } on ApiException catch (error) {
      if (!mounted) return;
      if (error.status == 401) {
        _loginEnded();
        return;
      }
      setState(() => _error = error.message);
    } finally {
      if (mounted) setState(() => _busyIds.remove(id));
    }
    await _load(force: true);
  }

  Future<void> _complete(String id) async {
    final code = _codeInputs[id]?.text.trim() ?? '';
    setState(() {
      _busyIds.add(id);
      _codeErrors.remove(id);
    });
    try {
      await api.workerComplete(id, code);
      if (!mounted) return;
      setState(() {
        _codeSent.remove(id);
        _codeInputs[id]?.clear();
      });
      FocusScope.of(context).unfocus();
      showToast(context, '$id is completed. The citizen now sees a green Resolved.');
    } on ApiException catch (error) {
      if (!mounted) return;
      if (error.status == 401) {
        _loginEnded();
        return;
      }
      setState(() => _codeErrors[id] = error.message);
    } finally {
      if (mounted) setState(() => _busyIds.remove(id));
    }
    await _load(force: true);
  }

  Future<void> _logout() async {
    try {
      await api.logout();
    } catch (_) {
      // The session ends on this device either way.
    }
    if (mounted) returnToLogin(context, workerTab: true);
  }

  void _show(WorkerView view) => setState(() => _view = view);

  int get _openTasks => _mine.where((item) => item['status'] == 'open').length;

  @override
  Widget build(BuildContext context) {
    final name = _text('name');
    final wide = isWideScreen(context);
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              PortalTopBar(
                tagline: 'Worker dashboard',
                onBrandTap: () => _show(WorkerView.available),
                links: [
                  NavLink('Complaints registered', () => _show(WorkerView.available),
                      selected: _view == WorkerView.available),
                  NavLink('Allotted tasks', () => _show(WorkerView.mine), selected: _view == WorkerView.mine),
                ],
                trailing: [AccountButton(name: name, details: workerDetails(widget.worker), onLogout: _logout)],
              ),
              HeroBanner(
                compact: true,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Welcome, $name',
                      style: const TextStyle(color: Palette.sky, fontSize: 15, fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 8),
                    const HeroHeadline(compact: true),
                    HeroLead(
                      '${_text('department')} · ${_text('zone')}, ${_text('ward')}. Accept a complaint, fix the problem, '
                      "and close it with the citizen's code.",
                    ),
                  ],
                ),
              ),
              PageWidth(
                child: Padding(
                  padding: const EdgeInsets.only(top: 26, bottom: 26),
                  child: wide
                      ? Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            SizedBox(width: 280, child: _sideNav(column: true)),
                            const SizedBox(width: 22),
                            Expanded(child: _content()),
                          ],
                        )
                      : Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [_sideNav(column: false), const SizedBox(height: 16), _content()],
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

  /// "Complaints registered" and "Allotted tasks", each with a count. A column at the left on wide screens.
  Widget _sideNav({required bool column}) {
    final available = _sideCard(
      Icons.assignment_turned_in_outlined,
      'Complaints registered',
      _available.length,
      WorkerView.available,
    );
    final mine = _sideCard(Icons.how_to_reg_outlined, 'Allotted tasks', _openTasks, WorkerView.mine);
    if (!column) {
      return Row(
        children: [Expanded(child: available), const SizedBox(width: 12), Expanded(child: mine)],
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        available,
        const SizedBox(height: 14),
        mine,
        const SizedBox(height: 14),
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Palette.white,
            border: Border.all(color: Palette.line),
            borderRadius: BorderRadius.circular(12),
          ),
          child: const Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('How it works',
                  style: TextStyle(fontSize: TextSizes.label, fontWeight: FontWeight.w700, color: Palette.navy)),
              SizedBox(height: 6),
              Text(
                '1. Accept a complaint. The citizen sees "Allotted" and "Work in progress".\n'
                '2. Fix the problem on the ground.\n'
                '3. Press "Mark as completed". A code goes to the citizen\'s mobile; enter it to close the complaint.',
                style: TextStyle(fontSize: TextSizes.small, color: Palette.labelText, height: 1.55),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _sideCard(IconData icon, String label, int count, WorkerView view) {
    final selected = _view == view;
    final phone = isPhone(context);
    return Semantics(
      selected: selected,
      button: true,
      child: Material(
        color: selected ? Palette.white : Palette.sectionBg,
        borderRadius: BorderRadius.circular(12),
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: () => _show(view),
          child: Container(
            padding: EdgeInsets.symmetric(horizontal: phone ? 12 : 18, vertical: phone ? 14 : 20),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: selected ? Palette.primary : Palette.cardEdge, width: selected ? 1.6 : 1),
              boxShadow: selected
                  ? const [BoxShadow(color: Color(0x1F023668), blurRadius: 14, offset: Offset(0, 4))]
                  : null,
            ),
            child: Row(
              children: [
                Icon(icon, size: phone ? 22 : 26, color: Palette.navy),
                SizedBox(width: phone ? 8 : 12),
                Expanded(
                  child: Text(
                    label,
                    style: TextStyle(
                      fontSize: phone ? 14 : 16.5,
                      fontWeight: FontWeight.w700,
                      color: Palette.navy,
                    ),
                  ),
                ),
                const SizedBox(width: 6),
                Container(
                  constraints: const BoxConstraints(minWidth: 26),
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(color: Palette.primary, borderRadius: BorderRadius.circular(999)),
                  child: Text(
                    '$count',
                    textAlign: TextAlign.center,
                    style: const TextStyle(color: Palette.white, fontSize: 13, fontWeight: FontWeight.w700),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _content() {
    final mine = _view == WorkerView.mine;
    final items = mine ? _mine : _available;
    final updated = _updated;
    final error = _error;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TitleCard(
          icon: mine ? Icons.how_to_reg_outlined : Icons.assignment_turned_in_outlined,
          title: mine ? 'Allotted tasks' : 'Complaints registered',
          help: mine
              ? "Complaints you accepted. Mark each one completed with the citizen's code."
              : 'Open complaints that no worker has taken yet. Your zone comes first.',
          total: items.length,
          totalLabel: mine ? 'Total tasks allotted to you' : 'Total complaints registered',
        ),
        const SizedBox(height: 14),
        Wrap(
          spacing: 12,
          runSpacing: 6,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            LiveIndicator(
              text: _offline
                  ? 'Cannot reach the server'
                  : (updated == null ? 'Live' : 'Live · updated ${formatClock(updated)}'),
              paused: _offline,
            ),
            if (error != null) Text(error, style: const TextStyle(color: Palette.error, fontWeight: FontWeight.w600)),
          ],
        ),
        const SizedBox(height: 12),
        if (!_loaded)
          const Padding(padding: EdgeInsets.all(20), child: Center(child: CircularProgressIndicator()))
        else if (items.isEmpty)
          EmptyBox(
            icon: Icons.inbox_outlined,
            text: mine
                ? 'You have not accepted a complaint yet. Accept one from Complaints registered.'
                : 'No open complaints are waiting right now. New ones appear here by themselves.',
          )
        else
          for (final item in items) _card(item, mine: mine),
      ],
    );
  }

  Widget _card(Map<String, dynamic> item, {required bool mine}) {
    String text(String key) => item[key]?.toString() ?? '';
    final id = text('id');
    final open = text('status') == 'open';
    final busy = _busyIds.contains(id);
    final landmark = text('landmark');
    final where = text('problem_address').isEmpty
        ? 'Not given'
        : '${text('problem_address')}${landmark.isEmpty ? '' : ' ($landmark)'}';
    // Completed: this worker closed it with the citizen's code. It can also be resolved another way (an officer).
    final done = item['work_status'] == 'completed';
    final Widget side;
    if (mine && done) {
      side = StatusPill.resolved('Completed');
    } else if (mine && open) {
      side = StatusPill.accepted();
    } else if (mine) {
      side = officerStatusPill(item);
    } else {
      side = StatusPill.registered('Waiting for a worker');
    }
    final showDetails = _detailsOpen.contains(id);
    final citizen = item['citizen'];
    final person = citizen is Map ? citizen : const <String, dynamic>{};
    String who(String key) => person[key]?.toString() ?? '';

    final actions = <Widget>[];
    if (!mine) {
      actions.add(PortalButton(
        label: 'Accept',
        icon: Icons.check_circle_outline,
        busy: busy,
        onPressed: () => _accept(id),
      ));
    } else if (open) {
      actions.add(PortalButton(
        label: 'Mark as completed',
        icon: Icons.key_outlined,
        busy: busy && !_codeSent.containsKey(id),
        onPressed: () => _requestCode(id),
      ));
    } else {
      actions.add(Text(
        done
            ? 'Completed on ${formatWhen(item['completed_at']?.toString(), empty: '-')}.'
            : text('status_text'),
        style: const TextStyle(fontSize: TextSizes.label, color: Palette.muted),
      ));
    }
    actions.add(PortalButton(
      label: showDetails ? 'Hide complainant details' : 'View complainant details',
      icon: Icons.person_outline,
      kind: ButtonKind.outline,
      onPressed: () => setState(() {
        if (!_detailsOpen.remove(id)) _detailsOpen.add(id);
      }),
    ));

    return JobCard(
      key: ValueKey<String>('${mine ? 'mine' : 'available'}-$id'),
      fresh: !mine && _fresh.contains(id),
      children: [
        JobTop(
          id: id,
          label: text('complaint_label'),
          pills: [
            if (!mine && _fresh.contains(id)) StatusPill.fresh(),
            if (item['overdue'] == true) StatusPill.overdue(),
          ],
          side: side,
        ),
        const SizedBox(height: 12),
        InfoGrid(rows: [
          MapEntry('Department', text('field')),
          MapEntry('Address of the problem', where),
          MapEntry('Zone and ward', text('zone').isEmpty ? '' : '${text('zone')}, ${text('ward')}'),
          MapEntry('Registered on', formatWhen(item['registered_at']?.toString(), empty: '')),
          MapEntry('Time limit', open ? formatWhen(item['deadline']?.toString()) : 'Not running'),
          MapEntry('Office in charge', text('current_office')),
        ]),
        ComplaintTextBox(text('complaint_text')),
        const SizedBox(height: 12),
        Wrap(spacing: 10, runSpacing: 10, crossAxisAlignment: WrapCrossAlignment.center, children: actions),
        if (showDetails)
          DetailsBox(
            icon: Icons.person_outline,
            title: 'Complainant details',
            rows: [
              MapEntry('Name', who('name')),
              MapEntry('Mobile number', who('mobile')),
              MapEntry('Home address', who('address')),
              MapEntry('Zone', who('zone')),
              MapEntry('Ward', who('ward')),
            ],
          ),
        if (mine && open && (_codeSent.containsKey(id) || item['code_sent'] == true)) _codeBox(id),
      ],
    );
  }

  /// After "Mark as completed": enter the code the citizen received. Only the right code completes the complaint.
  Widget _codeBox(String id) {
    final sent = _codeSent[id];
    final input = _codeInputs.putIfAbsent(id, () => TextEditingController());
    final error = _codeErrors[id];
    final busy = _busyIds.contains(id);
    final message = sent == null
        ? "A code was sent to the citizen's mobile. Ask the citizen for it and enter it here."
        : "A code was sent to the citizen's mobile ${sent['sent_to'] ?? ''}. Ask the citizen for it and enter it here. "
            'It lasts ${sent['minutes'] ?? 10} minutes.';
    return Container(
      margin: const EdgeInsets.only(top: 12),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(color: Palette.warnBg, borderRadius: BorderRadius.circular(10)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(message, style: const TextStyle(fontSize: TextSizes.label, color: Palette.warn)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              SizedBox(
                width: 180,
                child: TextField(
                  controller: input,
                  keyboardType: TextInputType.number,
                  inputFormatters: [FilteringTextInputFormatter.digitsOnly, LengthLimitingTextInputFormatter(6)],
                  style: const TextStyle(fontWeight: FontWeight.w700, letterSpacing: 4),
                  decoration: const InputDecoration(hintText: '6-digit code', fillColor: Palette.white),
                  onSubmitted: (_) => _complete(id),
                ),
              ),
              PortalButton(label: 'Verify and complete', small: true, busy: busy, onPressed: () => _complete(id)),
              PortalButton(
                label: 'Send a new code',
                small: true,
                kind: ButtonKind.outline,
                onPressed: busy ? null : () => _requestCode(id),
              ),
            ],
          ),
          if (error != null) ErrorText(error),
        ],
      ),
    );
  }
}
