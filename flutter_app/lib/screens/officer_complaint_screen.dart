import 'dart:async';

import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../theme.dart';
import '../widgets/account_button.dart';
import '../widgets/board.dart';
import '../widgets/common.dart';
import 'login_screen.dart';
import 'officer_home_screen.dart';

/// One complaint, as the officer sees it: the details, the history, and the actions (note, resolve, escalate).
/// It is checked again every 5 seconds, so a citizen's confirmation shows up here by itself.
class OfficerComplaintScreen extends StatefulWidget {
  const OfficerComplaintScreen({super.key, required this.officer, required this.complaintId});

  final Map<String, dynamic> officer;
  final String complaintId;

  @override
  State<OfficerComplaintScreen> createState() => _OfficerComplaintScreenState();
}

class _OfficerComplaintScreenState extends State<OfficerComplaintScreen> {
  final _note = TextEditingController();
  Map<String, dynamic>? _detail;
  String? _loadError;
  String? _actionError;
  bool _busy = false;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(const Duration(seconds: 5), (_) => _load());
  }

  @override
  void dispose() {
    _timer?.cancel();
    _note.dispose();
    super.dispose();
  }

  int _gen = 0; // goes up with every load, so an older answer that arrives late is ignored

  Future<void> _load() async {
    final gen = ++_gen;
    try {
      final detail = await api.officerDetail(widget.complaintId);
      if (!mounted || gen != _gen) return;
      setState(() {
        _detail = detail;
        _loadError = null;
      });
    } on ApiException catch (error) {
      if (!mounted || gen != _gen) return;
      if (error.status == 401) {
        officerLoginEnded(context);
        return;
      }
      setState(() => _loadError = error.message);
    }
  }

  Future<void> _run(String action) async {
    final note = _note.text.trim();
    if (note.isEmpty) {
      setState(() => _actionError = 'Write a note first.');
      return;
    }
    setState(() {
      _busy = true;
      _actionError = null;
    });
    try {
      await api.officerAction(widget.complaintId, action, note);
      if (!mounted) return;
      _note.clear();
      if (action == 'escalate') {
        // The complaint now belongs to the next officer, so it leaves this officer's list.
        Navigator.of(context).pop('${widget.complaintId} was escalated to the next level.');
        return;
      }
      await _load();
    } on ApiException catch (error) {
      if (mounted) setState(() => _actionError = error.message);
    } finally {
      if (mounted) setState(() => _busy = false);
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

  void _back() => Navigator.of(context).pop();

  @override
  Widget build(BuildContext context) {
    final detail = _detail;
    final loadError = _loadError;
    Widget body;
    if (detail == null) {
      body = Padding(
        padding: const EdgeInsets.symmetric(vertical: 40),
        child: Center(
          child: loadError == null
              ? const CircularProgressIndicator()
              : NoticeBox(text: loadError, tone: NoticeTone.error),
        ),
      );
    } else {
      body = _card(detail, loadError);
    }
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              PortalTopBar(
                tagline: 'Officer dashboard',
                onBrandTap: _back,
                links: [
                  NavLink('Complaints', _back),
                  NavLink(widget.complaintId, () {}, selected: true),
                ],
                trailing: [
                  AccountButton(
                    name: widget.officer['name']?.toString() ?? '',
                    details: officerDetails(widget.officer),
                    onLogout: _logout,
                  ),
                ],
              ),
              PageWidth(child: body),
              const PortalFooter(),
            ],
          ),
        ),
      ),
    );
  }

  /// The worker who accepted the complaint, with their department and mobile number.
  String _workerLine(Object? worker) {
    if (worker is! Map) return 'No worker has accepted it yet';
    return '${worker['name'] ?? ''} (${worker['department'] ?? ''}), ${worker['mobile'] ?? ''}';
  }

  Widget _card(Map<String, dynamic> d, String? loadError) {
    String text(String key) => d[key]?.toString() ?? '';
    final status = text('status');
    final path = d['path'];
    final events = d['events'];
    final zone = text('zone');
    final rows = <MapEntry<String, String>>[
      MapEntry('Citizen', text('citizen_name')),
      MapEntry('Mobile', text('citizen_contact')),
      MapEntry('Address of the problem', text('problem_address').isEmpty ? 'Not given' : text('problem_address')),
      MapEntry('Landmark', text('landmark').isEmpty ? 'None' : text('landmark')),
      MapEntry('Zone and ward', zone.isEmpty ? 'Not recorded' : '$zone, ${text('ward')}'),
      MapEntry('Worker', _workerLine(d['worker'])),
      MapEntry('With', text('current_office')),
      MapEntry('Assigned to', text('assigned_to')),
      MapEntry(
        'Time limit',
        status == 'awaiting_confirmation' ? 'Not running (waiting for the citizen)' : formatWhen(d['deadline']?.toString()),
      ),
    ];
    final actionError = _actionError;
    return FormCard(
      icon: Icons.description_outlined,
      title: text('id'),
      subtitle: '${text('complaint_label')} · ${text('field')}',
      headTrailing: Wrap(
        spacing: 8,
        runSpacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          officerStatusPill(d),
          if (d['urgent'] == true) Pill.overdue('Urgent'),
          if (d['overdue'] == true) Pill.overdue(),
          PortalButton(
            label: 'Back to complaints',
            icon: Icons.arrow_back,
            small: true,
            kind: ButtonKind.outline,
            onPressed: _back,
          ),
        ],
      ),
      child: TwoColumns(
        left: [
          if (loadError != null) NoticeBox(text: loadError, tone: NoticeTone.error),
          NoticeBox(text: text('status_text'), tone: NoticeTone.info),
          for (final row in rows)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: 120,
                    child: Text(row.key, style: const TextStyle(fontSize: 14.5, color: Palette.muted)),
                  ),
                  Expanded(
                    child: Text(row.value, style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600)),
                  ),
                ],
              ),
            ),
          const SizedBox(height: 8),
          const _Heading('Complaint'),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Palette.page,
              border: Border.all(color: Palette.line),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(text('complaint_text'), style: const TextStyle(fontSize: TextSizes.body, height: 1.5)),
          ),
          const SizedBox(height: 12),
          const _Heading('Route'),
          Text(
            path is List ? path.join('  >  ') : '',
            style: const TextStyle(fontSize: TextSizes.label, color: Palette.muted),
          ),
          const SizedBox(height: 14),
        ],
        right: [
          const _Heading('Action'),
          LabeledField(
            label: 'Note (needed for every action)',
            required: true,
            child: TextField(
              controller: _note,
              minLines: 3,
              maxLines: 6,
              maxLength: 1000,
              decoration: const InputDecoration(
                hintText: 'What was done, or why this is being passed on',
                counterText: '',
              ),
            ),
          ),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              PortalButton(
                label: 'Mark resolved',
                icon: Icons.check_circle_outline,
                busy: _busy,
                onPressed: d['can_resolve'] == true ? () => _run('resolve') : null,
              ),
              PortalButton(
                label: 'Add note',
                kind: ButtonKind.outline,
                onPressed: d['can_note'] == true && !_busy ? () => _run('note') : null,
              ),
              PortalButton(
                label: 'Escalate to next level',
                kind: ButtonKind.danger,
                onPressed: d['can_escalate'] == true && !_busy ? () => _run('escalate') : null,
              ),
            ],
          ),
          const Padding(
            padding: EdgeInsets.only(top: 8),
            child: Text(
              'Marking resolved does not close the complaint. The citizen confirms it. '
              'If the citizen says it is still not fixed, it goes to the next level.',
              style: TextStyle(fontSize: TextSizes.tiny, color: Palette.muted),
            ),
          ),
          if (actionError != null) ErrorText(actionError),
          const SizedBox(height: 16),
          const _Heading('History'),
          if (events is List)
            for (final event in events)
              if (event is Map)
                Container(
                  padding: const EdgeInsets.symmetric(vertical: 8),
                  decoration: const BoxDecoration(border: Border(bottom: BorderSide(color: Palette.line))),
                  child: Text.rich(
                    TextSpan(
                      children: [
                        TextSpan(
                          text: '${formatWhen(event['at']?.toString())} (${event['actor'] ?? ''}) - ',
                          style: const TextStyle(fontSize: TextSizes.small, color: Palette.muted),
                        ),
                        TextSpan(
                          text: event['message']?.toString() ?? '',
                          style: const TextStyle(fontSize: TextSizes.label, color: Palette.text),
                        ),
                      ],
                    ),
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
      padding: const EdgeInsets.only(bottom: 6),
      child: Text(text, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700, color: Palette.navy)),
    );
  }
}
