import 'dart:async';

import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../theme.dart';
import 'board.dart';
import 'common.dart';

/// "Your complaints" at the side of Register Complaint: every complaint the citizen filed, each with its
/// complaint ID and Completed or Not completed. It checks again every 5 seconds.
class YourComplaintsPanel extends StatefulWidget {
  const YourComplaintsPanel({super.key, required this.onOpen, required this.onLoginEnded, this.refresh = 0});

  /// Opens a complaint on Track Complaint.
  final ValueChanged<String> onOpen;

  /// Called when the login has ended (the server answers 401).
  final VoidCallback onLoginEnded;

  /// Change this number to load the list again straight away, for example after a new complaint.
  final int refresh;

  @override
  State<YourComplaintsPanel> createState() => _YourComplaintsPanelState();
}

class _YourComplaintsPanelState extends State<YourComplaintsPanel> {
  List<Map<String, dynamic>> _items = <Map<String, dynamic>>[];
  bool _loaded = false;
  bool _offline = false;
  int _gen = 0; // goes up with every load, so an older answer that arrives late is ignored
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _load();
    _timer = Timer.periodic(const Duration(seconds: 5), (_) => _load());
  }

  @override
  void didUpdateWidget(YourComplaintsPanel oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.refresh != widget.refresh) _load();
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    final gen = ++_gen;
    try {
      final items = await api.citizenComplaints();
      if (!mounted || gen != _gen) return;
      setState(() {
        _items = items;
        _loaded = true;
        _offline = false;
      });
    } on ApiException catch (error) {
      if (!mounted || gen != _gen) return;
      if (error.status == 401) {
        widget.onLoginEnded();
        return;
      }
      setState(() => _offline = true);
    }
  }

  static bool _done(Map<String, dynamic> item) {
    final status = item['status']?.toString() ?? '';
    return status == 'closed' || status == 'awaiting_confirmation';
  }

  @override
  Widget build(BuildContext context) {
    final completed = _items.where(_done).length;
    final count = !_loaded
        ? 'Loading ...'
        : (_items.isEmpty
            ? 'None yet'
            : '${_items.length} registered · $completed completed · ${_items.length - completed} not completed');
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 24, bottom: 24),
      padding: const EdgeInsets.fromLTRB(18, 18, 18, 14),
      decoration: BoxDecoration(
        color: Palette.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFCFE0F0)),
        boxShadow: const [BoxShadow(color: Color(0x12023668), blurRadius: 10, offset: Offset(0, 2))],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              const Icon(Icons.assignment_turned_in_outlined, size: 32, color: Palette.navy),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('Your complaints',
                        style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: Palette.navy)),
                    Text(count, style: const TextStyle(fontSize: TextSizes.small, color: Palette.muted)),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerLeft,
            child: LiveIndicator(text: _offline ? 'Cannot reach the server' : 'Live', paused: _offline),
          ),
          const SizedBox(height: 8),
          if (_loaded && _items.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: Text(
                'You have not registered a complaint yet. Your complaints will appear here.',
                style: TextStyle(fontSize: TextSizes.label, color: Palette.muted),
              ),
            ),
          for (final item in _items) _row(item),
        ],
      ),
    );
  }

  Widget _row(Map<String, dynamic> item) {
    final id = item['id']?.toString() ?? '';
    return InkWell(
      key: ValueKey<String>(id),
      onTap: () => widget.onOpen(id),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 2),
        decoration: const BoxDecoration(border: Border(top: BorderSide(color: Palette.line))),
        child: Row(
          children: [
            Expanded(
              child: Text(
                id,
                style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w700, color: Palette.navy),
              ),
            ),
            const SizedBox(width: 10),
            _done(item) ? StatusPill.resolved('Completed') : StatusPill.allotted('Not completed'),
          ],
        ),
      ),
    );
  }
}
