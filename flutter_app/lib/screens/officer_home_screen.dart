import 'dart:async';

import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../theme.dart';
import '../widgets/account_button.dart';
import '../widgets/board.dart';
import '../widgets/common.dart';
import 'login_screen.dart';
import 'officer_complaint_screen.dart';

/// The officer's details for the account icon.
List<MapEntry<String, String>> officerDetails(Map<String, dynamic> officer) {
  String text(String key) => officer[key]?.toString() ?? '';
  return [
    MapEntry('Name', text('name')),
    MapEntry('Username', text('username')),
    MapEntry('Level', text('level_label')),
    MapEntry('Field', text('field_label')),
  ];
}

/// Sends an officer whose login has ended (at midnight, India time) back to the Officer Login tab.
void officerLoginEnded(BuildContext context) {
  returnToLogin(
    context,
    message: 'Log in as an officer to continue. Officer logins end at midnight every day (India time).',
    isError: true,
    officerTab: true,
  );
}

/// The two screens on the officer dashboard.
enum OfficerView { complaints, notices }

/// The officer dashboard. It checks for new complaints and notices every 5 seconds and marks new ones.
/// A notice is a complaint that passed its time limit; a new notice opens the Notices screen by itself.
class OfficerHomeScreen extends StatefulWidget {
  const OfficerHomeScreen({super.key, required this.officer});

  final Map<String, dynamic> officer;

  @override
  State<OfficerHomeScreen> createState() => _OfficerHomeScreenState();
}

class _OfficerHomeScreenState extends State<OfficerHomeScreen> {
  List<Map<String, dynamic>> _items = <Map<String, dynamic>>[];
  Set<String>? _seen;
  final Set<String> _newIds = <String>{};
  bool _loaded = false;
  bool _offline = false;
  bool _loading = false;
  int _gen = 0; // goes up with every load, so an older answer that arrives late is ignored
  DateTime? _updated;
  String? _notice;
  Timer? _timer;

  OfficerView _view = OfficerView.complaints;
  List<Map<String, dynamic>> _notices = <Map<String, dynamic>>[];
  Set<String>? _noticeIds; // notices already shown, to mark new ones
  final Set<String> _freshNotices = <String>{};
  bool _noticesLoaded = false;
  bool _noticesOffline = false;

  bool get _isHead => widget.officer['is_district_head'] == true;

  @override
  void initState() {
    super.initState();
    _load(force: true);
    _timer = Timer.periodic(const Duration(seconds: 5), (_) => _load());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load({bool force = false}) async {
    if (_loading && !force) return;
    final gen = ++_gen;
    _loading = true;
    try {
      await _loadNotices(gen);
      if (!mounted || gen != _gen) return;
      final items = await api.officerComplaints();
      if (!mounted || gen != _gen) return;
      final ids = items.map((item) => item['id']?.toString() ?? '').toSet();
      final seen = _seen;
      setState(() {
        if (seen != null) _newIds.addAll(ids.difference(seen));
        _newIds.removeWhere((id) => !ids.contains(id));
        _seen = ids;
        _items = items;
        _loaded = true;
        _offline = false;
        _updated = DateTime.now();
      });
    } on ApiException catch (error) {
      if (!mounted || gen != _gen) return;
      if (error.status == 401) {
        // Only when this screen is in front; an open complaint screen above it sends the officer back itself.
        if (ModalRoute.of(context)?.isCurrent ?? true) officerLoginEnded(context);
        return;
      }
      setState(() => _offline = true);
    } finally {
      if (gen == _gen) _loading = false;
    }
  }

  /// Loads the notices. On the first load, or when a new notice arrives, the Notices screen opens by itself.
  Future<void> _loadNotices(int gen) async {
    try {
      final notices = await api.officerNotices();
      if (!mounted || gen != _gen) return;
      String key(Map<String, dynamic> notice) => notice['notice_id']?.toString() ?? '';
      final ids = notices.map(key).toSet();
      final known = _noticeIds;
      final added = known == null
          ? <Map<String, dynamic>>[]
          : notices.where((notice) => !known.contains(key(notice))).toList();
      setState(() {
        _freshNotices
          ..addAll(added.map(key))
          ..removeWhere((id) => !ids.contains(id));
        if ((known == null && notices.isNotEmpty) || added.isNotEmpty) _view = OfficerView.notices;
        _noticeIds = ids;
        _notices = notices;
        _noticesLoaded = true;
        _noticesOffline = false;
      });
      if (added.isNotEmpty) {
        final which = added.map((notice) => notice['complaint_id']?.toString() ?? '').join(', ');
        showToast(context, 'New notice: $which passed the time limit.');
      }
    } on ApiException catch (error) {
      if (error.status == 401) rethrow;
      if (mounted) setState(() => _noticesOffline = true);
    }
  }

  void _show(OfficerView view) => setState(() => _view = view);

  Future<void> _open(String id) async {
    setState(() => _newIds.remove(id));
    final message = await Navigator.of(context).push<String>(
      MaterialPageRoute<String>(builder: (_) => OfficerComplaintScreen(officer: widget.officer, complaintId: id)),
    );
    if (!mounted) return;
    if (message != null) setState(() => _notice = message);
    _load(force: true);
  }

  Future<void> _checkOverdue() async {
    try {
      final moved = await api.checkOverdue();
      if (!mounted) return;
      setState(() => _notice = 'Checked. $moved complaint(s) moved on past their time limit.');
      _load(force: true);
    } on ApiException catch (error) {
      if (mounted) setState(() => _notice = error.message);
    }
  }

  Future<void> _logout() async {
    try {
      await api.logout();
    } catch (_) {
      // The session ends on this device either way.
    }
    if (mounted) returnToLogin(context, officerTab: true);
  }

  int _count(bool Function(Map<String, dynamic> item) test) => _items.where(test).length;

  @override
  Widget build(BuildContext context) {
    final name = widget.officer['name']?.toString() ?? '';
    final level = widget.officer['level_label']?.toString() ?? '';
    final field = widget.officer['field_label']?.toString() ?? '';
    final notice = _notice;
    final updated = _updated;
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              PortalTopBar(
                tagline: 'Officer dashboard',
                links: [
                  NavLink('Complaints', () => _show(OfficerView.complaints), selected: _view == OfficerView.complaints),
                  NavLink(
                    'Notices',
                    () => _show(OfficerView.notices),
                    selected: _view == OfficerView.notices,
                    badge: _notices.length,
                  ),
                ],
                trailing: [AccountButton(name: name, details: officerDetails(widget.officer), onLogout: _logout)],
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
                    Text(
                      'Officer Dashboard',
                      style: TextStyle(
                        color: Palette.white,
                        fontSize: isPhone(context) ? TextSizes.headlinePhone : TextSizes.headlineCompact,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                    HeroLead('$level · $field. Your login ends at midnight (India time).'),
                  ],
                ),
              ),
              if (_view == OfficerView.notices)
                PageWidth(child: _noticesView())
              else
                PageWidth(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const SizedBox(height: 26),
                      NumbersStrip(
                        title: _isHead ? 'All Complaints in Numbers' : 'Your Complaints in Numbers',
                        subtitle: 'Updates on its own every few seconds.',
                        stats: [
                          StatData(Icons.inbox_outlined, Tone.blue, _count((item) => item['status'] == 'open'), 'Open'),
                          StatData(Icons.schedule, Tone.orange, _count((item) => item['overdue'] == true), 'Time limit passed'),
                          StatData(Icons.people_outline, Tone.yellow,
                              _count((item) => item['status'] == 'awaiting_confirmation'), 'Waiting for citizen'),
                          StatData(Icons.check_circle_outline, Tone.green, _count((item) => item['status'] == 'closed'), 'Closed'),
                        ],
                      ),
                      Panel(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            SectionHead(
                              title: _isHead ? 'All complaints (District Head Office)' : 'Complaints assigned to you',
                              subtitle: _isHead
                                  ? 'You see every complaint. Escalated and unassigned complaints need your attention first.'
                                  : 'Tap a complaint to see its details and act on it.',
                              trailing: Wrap(
                                spacing: 10,
                                runSpacing: 8,
                                crossAxisAlignment: WrapCrossAlignment.center,
                                children: [
                                  LiveIndicator(
                                    text: _offline
                                        ? 'Cannot reach the server'
                                        : (updated == null ? 'Live' : 'Live · updated ${formatClock(updated)}'),
                                    paused: _offline,
                                  ),
                                  PortalButton(
                                    label: 'Refresh',
                                    icon: Icons.refresh,
                                    small: true,
                                    kind: ButtonKind.outline,
                                    onPressed: () => _load(force: true),
                                  ),
                                  if (_isHead)
                                    PortalButton(
                                      label: 'Check passed time limits now',
                                      icon: Icons.schedule,
                                      small: true,
                                      kind: ButtonKind.outline,
                                      onPressed: _checkOverdue,
                                    ),
                                ],
                              ),
                            ),
                            if (notice != null)
                              Padding(
                                padding: const EdgeInsets.only(top: 12),
                                child: NoticeBox(text: notice, tone: NoticeTone.info),
                              ),
                            const SizedBox(height: 12),
                            _list(),
                          ],
                        ),
                      ),
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

  Widget _list() {
    if (!_loaded) {
      return const Padding(padding: EdgeInsets.all(16), child: Center(child: CircularProgressIndicator()));
    }
    if (_items.isEmpty) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 8),
        child: Text(
          'Nothing here right now. New complaints appear here on their own.',
          style: TextStyle(fontSize: TextSizes.label, color: Palette.muted),
        ),
      );
    }
    return isWideScreen(context) ? _table() : _cards();
  }

  static const List<int> _flex = <int>[16, 18, 10, 14, 20, 13, 11];
  static const List<String> _headings = <String>[
    'ID',
    'Complaint',
    'Field',
    'Zone and ward',
    'With',
    'Time limit',
    'Status',
  ];

  String _place(Map<String, dynamic> item) {
    final zone = item['zone']?.toString() ?? '';
    return zone.isEmpty ? 'Not recorded' : '$zone, ${item['ward']}';
  }

  Widget _deadline(Map<String, dynamic> item) {
    final open = item['status'] == 'open';
    return Wrap(
      spacing: 6,
      runSpacing: 4,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        Text(open ? formatWhen(item['deadline']?.toString(), empty: 'None') : 'Not running'),
        if (item['overdue'] == true) Pill.overdue('Passed'),
      ],
    );
  }

  Widget _table() {
    const cellStyle = TextStyle(fontSize: TextSizes.label, color: Palette.text);
    final header = Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
      decoration: const BoxDecoration(
        color: Palette.page,
        border: Border(bottom: BorderSide(color: Palette.line, width: 2)),
      ),
      child: Row(
        children: [
          for (var i = 0; i < _headings.length; i++)
            Expanded(
              flex: _flex[i],
              child: Text(
                _headings[i].toUpperCase(),
                style: const TextStyle(
                  fontSize: TextSizes.tiny,
                  fontWeight: FontWeight.w600,
                  color: Palette.muted,
                  letterSpacing: 0.5,
                ),
              ),
            ),
        ],
      ),
    );
    final rows = <Widget>[header];
    for (final item in _items) {
      final id = item['id']?.toString() ?? '';
      final isNew = _newIds.contains(id);
      final cells = <Widget>[
        Wrap(
          spacing: 6,
          runSpacing: 4,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Text(id, style: const TextStyle(fontWeight: FontWeight.w700, color: Palette.navy)),
            if (isNew) Pill.newItem(),
          ],
        ),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(item['complaint_label']?.toString() ?? '', style: cellStyle),
            if ((item['problem_address']?.toString() ?? '').isNotEmpty)
              Text(
                item['problem_address'].toString(),
                style: const TextStyle(fontSize: TextSizes.tiny, color: Palette.muted),
              ),
          ],
        ),
        Text(item['field']?.toString() ?? '', style: cellStyle),
        Text(_place(item), style: cellStyle),
        Text(item['current_office']?.toString() ?? '', style: cellStyle),
        DefaultTextStyle.merge(style: cellStyle, child: _deadline(item)),
        Align(alignment: Alignment.centerLeft, child: officerStatusPill(item)),
      ];
      rows.add(
        InkWell(
          key: ValueKey<String>(id),
          onTap: () => _open(id),
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 11),
            decoration: BoxDecoration(
              color: isNew ? const Color(0xFFFFF6D6) : null,
              border: const Border(bottom: BorderSide(color: Palette.line)),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (var i = 0; i < cells.length; i++)
                  Expanded(
                    flex: _flex[i],
                    child: Padding(padding: const EdgeInsets.only(right: 8), child: cells[i]),
                  ),
              ],
            ),
          ),
        ),
      );
    }
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: rows);
  }

  Widget _cards() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final item in _items) _card(item),
      ],
    );
  }

  Widget _card(Map<String, dynamic> item) {
    final id = item['id']?.toString() ?? '';
    final isNew = _newIds.contains(id);
    return InkWell(
      key: ValueKey<String>(id),
      onTap: () => _open(id),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 6),
        decoration: BoxDecoration(
          color: isNew ? const Color(0xFFFFF6D6) : null,
          border: const Border(top: BorderSide(color: Palette.line)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Wrap(
              spacing: 8,
              runSpacing: 6,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text(id, style: const TextStyle(fontWeight: FontWeight.w700, color: Palette.navy)),
                officerStatusPill(item),
                if (isNew) Pill.newItem(),
                if (item['overdue'] == true) Pill.overdue(),
              ],
            ),
            const SizedBox(height: 4),
            Text('${item['complaint_label'] ?? ''} (${item['field'] ?? ''})'),
            if ((item['problem_address']?.toString() ?? '').isNotEmpty)
              Text(
                'At: ${item['problem_address']}',
                style: const TextStyle(fontSize: TextSizes.small, color: Palette.muted),
              ),
            const SizedBox(height: 2),
            Text(
              '${_place(item)}  ·  With: ${item['current_office'] ?? ''}',
              style: const TextStyle(fontSize: TextSizes.small, color: Palette.muted),
            ),
            if (item['status'] == 'open')
              Text(
                'Time limit: ${formatWhen(item['deadline']?.toString(), empty: 'None')}',
                style: const TextStyle(fontSize: TextSizes.small, color: Palette.muted),
              ),
          ],
        ),
      ),
    );
  }

  // Notices: complaints that passed their time limit

  Widget _noticesView() {
    final Widget list;
    if (!_noticesLoaded) {
      list = const Padding(padding: EdgeInsets.all(20), child: Center(child: CircularProgressIndicator()));
    } else if (_notices.isEmpty) {
      list = const EmptyBox(
        icon: Icons.notifications_none,
        text: 'No notices. When a complaint passes its time limit, it appears here by itself.',
      );
    } else {
      list = Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [for (final notice in _notices) _noticeCard(notice)],
      );
    }
    final updated = _updated;
    return Padding(
      padding: const EdgeInsets.only(top: 26, bottom: 26),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TitleCard(
            icon: Icons.campaign_outlined,
            title: 'Notices received',
            help: 'Complaints that passed their time limit, with the department and office in charge, the citizen, '
                'and the worker who accepted it.',
            total: _notices.length,
            totalLabel: 'Total no of notices received',
            totalIcon: Icons.notifications_none,
          ),
          const SizedBox(height: 14),
          Wrap(
            alignment: WrapAlignment.spaceBetween,
            crossAxisAlignment: WrapCrossAlignment.center,
            spacing: 12,
            runSpacing: 8,
            children: [
              LiveIndicator(
                text: _noticesOffline
                    ? 'Cannot reach the server'
                    : (updated == null ? 'Live' : 'Live · updated ${formatClock(updated)}'),
                paused: _noticesOffline,
              ),
              PortalButton(
                label: 'Back to complaints',
                icon: Icons.chevron_left,
                small: true,
                kind: ButtonKind.outline,
                onPressed: () => _show(OfficerView.complaints),
              ),
            ],
          ),
          const SizedBox(height: 12),
          list,
        ],
      ),
    );
  }

  Widget _noticeCard(Map<String, dynamic> notice) {
    String text(String key) => notice[key]?.toString() ?? '';
    final key = text('notice_id');
    final isNew = _freshNotices.contains(key);
    final now = text('now_status');
    final resolved = now == 'closed' || now == 'awaiting_confirmation';
    final landmark = text('landmark');
    final where = text('problem_address').isEmpty
        ? 'Not given'
        : '${text('problem_address')}${landmark.isEmpty ? '' : ' ($landmark)'}';
    final citizen = notice['citizen'];
    final person = citizen is Map ? citizen : const <String, dynamic>{};
    String who(String field) => person[field]?.toString() ?? '';
    final worker = notice['worker'];
    return JobCard(
      key: ValueKey<String>('notice-$key'),
      alert: true,
      fresh: isNew,
      children: [
        JobTop(
          id: text('complaint_id'),
          label: text('complaint_label'),
          pills: [StatusPill.overdue('Time limit crossed'), if (isNew) StatusPill.fresh()],
          side: resolved ? StatusPill.resolved() : StatusPill.allotted('Still open'),
        ),
        const SizedBox(height: 12),
        InfoGrid(rows: [
          MapEntry('Department', text('department')),
          MapEntry('Office in charge', text('office')),
          MapEntry('Moved to', text('moved_to').isEmpty ? 'Already at the last level' : text('moved_to')),
          MapEntry('Time limit was', formatWhen(notice['deadline']?.toString())),
          MapEntry('Noticed on', formatWhen(notice['created_at']?.toString(), empty: '')),
          MapEntry('Registered on', formatWhen(notice['registered_at']?.toString(), empty: '')),
          MapEntry('Address of the problem', where),
          MapEntry('Zone and ward', text('zone').isEmpty ? '' : '${text('zone')}, ${text('ward')}'),
        ]),
        ComplaintTextBox(text('complaint_text')),
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
        DetailsBox(
          icon: Icons.engineering_outlined,
          title: 'Worker who accepted it',
          empty: 'No worker had accepted it when the time limit passed.',
          rows: worker is Map
              ? [
                  MapEntry('Name', worker['name']?.toString() ?? ''),
                  MapEntry('Mobile number', worker['mobile']?.toString() ?? ''),
                  MapEntry('Department', worker['department']?.toString() ?? ''),
                  MapEntry('Accepted on', formatWhen(worker['accepted_at']?.toString(), empty: '')),
                ]
              : const <MapEntry<String, String>>[],
        ),
      ],
    );
  }
}
