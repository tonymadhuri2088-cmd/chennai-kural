import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../theme.dart';
import 'common.dart';

/// The status pills that match the web pages: a green Resolved, an orange Allotted, and so on.
class StatusPill extends StatelessWidget {
  const StatusPill(this.text, {super.key, required this.background, required this.foreground, this.tick = false});

  final String text;
  final Color background;
  final Color foreground;

  /// Shows a tick before the words, as on the green Resolved pill.
  final bool tick;

  /// Green, with a tick.
  factory StatusPill.resolved([String text = 'Resolved']) =>
      StatusPill(text, background: Palette.successBg, foreground: Palette.success, tick: true);

  factory StatusPill.allotted([String text = 'Allotted · Work in progress']) =>
      StatusPill(text, background: const Color(0xFFFFE9DC), foreground: const Color(0xFFA8420C));

  factory StatusPill.accepted([String text = 'Accepted · Work in progress']) =>
      StatusPill(text, background: Palette.successBg, foreground: Palette.success, tick: true);

  factory StatusPill.registered([String text = 'Registered']) =>
      StatusPill(text, background: const Color(0xFFDDEEFF), foreground: const Color(0xFF0A56A8));

  factory StatusPill.overdue([String text = 'Time limit passed']) =>
      StatusPill(text, background: Palette.errorBg, foreground: Palette.error);

  factory StatusPill.fresh() => const StatusPill('New', background: Palette.primaryBright, foreground: Palette.white);

  /// What a citizen sees for one of their complaints: a green Resolved once an officer or a worker has resolved
  /// it, "Allotted · Work in progress" while a worker has it, and "Registered" before that.
  /// [short] uses "Allotted" alone, for small chips where the complaint ID needs the room.
  factory StatusPill.forCitizen(Map<String, dynamic> item, {bool short = false}) {
    final status = item['status']?.toString() ?? '';
    if (status == 'closed' || status == 'awaiting_confirmation') return StatusPill.resolved();
    if (item['work_status'] == 'allotted') return short ? StatusPill.allotted('Allotted') : StatusPill.allotted();
    return StatusPill.registered();
  }

  @override
  Widget build(BuildContext context) {
    final style = TextStyle(fontSize: TextSizes.tiny, fontWeight: FontWeight.w600, color: foreground);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
      decoration: BoxDecoration(color: background, borderRadius: BorderRadius.circular(999)),
      // One Text with the tick inside: it stays on one line in a Row, and wraps in a narrow table cell.
      child: Text.rich(
        TextSpan(
          children: [
            if (tick)
              WidgetSpan(
                alignment: PlaceholderAlignment.middle,
                child: Padding(
                  padding: const EdgeInsets.only(right: 4),
                  child: Icon(Icons.check, size: 13, color: foreground),
                ),
              ),
            TextSpan(text: text),
          ],
        ),
        style: style,
      ),
    );
  }
}

/// The status an officer sees: a green Resolved once closed, an orange Allotted while a worker has it,
/// and otherwise Open or Waiting for citizen.
Widget officerStatusPill(Map<String, dynamic> item) {
  final status = item['status']?.toString() ?? '';
  if (status == 'closed') return StatusPill.resolved();
  if (item['work_status'] == 'allotted') return StatusPill.allotted();
  return Pill.status(status, forOfficer: true);
}

/// The light blue card at the top of a list: a large icon, the title, a line of help, and a total at the right.
class TitleCard extends StatelessWidget {
  const TitleCard({
    super.key,
    required this.icon,
    required this.title,
    required this.help,
    required this.total,
    required this.totalLabel,
    this.totalIcon = Icons.description_outlined,
  });

  final IconData icon;
  final String title;
  final String help;
  final int total;
  final String totalLabel;
  final IconData totalIcon;

  @override
  Widget build(BuildContext context) {
    final phone = isPhone(context);
    final words = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          title,
          style: TextStyle(
            fontSize: phone ? TextSizes.formTitlePhone : 32,
            fontWeight: FontWeight.w800,
            color: Palette.navy,
          ),
        ),
        const SizedBox(height: 4),
        Text(help, style: const TextStyle(fontSize: TextSizes.label, color: Palette.muted)),
      ],
    );
    final count = Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(totalIcon, size: 28, color: Palette.primary),
        const SizedBox(width: 10),
        Flexible(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                '$total',
                style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w800, color: Palette.navy, height: 1.1),
              ),
              Text(
                totalLabel,
                style: const TextStyle(fontSize: TextSizes.label, fontWeight: FontWeight.w600, color: Palette.primary),
              ),
            ],
          ),
        ),
      ],
    );
    final Widget body;
    if (phone) {
      body = Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(icon, size: 40, color: Palette.navy),
              const SizedBox(width: 12),
              Expanded(child: words),
            ],
          ),
          const Divider(color: Palette.cardEdge, height: 24),
          count,
        ],
      );
    } else {
      body = Row(
        children: [
          Icon(icon, size: 56, color: Palette.navy),
          const SizedBox(width: 18),
          Expanded(child: words),
          Container(width: 1, height: 56, color: Palette.cardEdge, margin: const EdgeInsets.symmetric(horizontal: 20)),
          // A width limit, so the words in the count can wrap inside this Row.
          ConstrainedBox(constraints: const BoxConstraints(maxWidth: 280), child: count),
        ],
      );
    }
    return Container(
      padding: EdgeInsets.symmetric(horizontal: phone ? 16 : 26, vertical: phone ? 16 : 20),
      decoration: BoxDecoration(
        color: Palette.sectionBg,
        border: Border.all(color: Palette.cardEdge),
        borderRadius: BorderRadius.circular(14),
      ),
      child: body,
    );
  }
}

/// Labels with their values under them, in as many columns as fit. A label never splits from its value.
class InfoGrid extends StatelessWidget {
  const InfoGrid({super.key, required this.rows, this.minColumnWidth = 200});

  final List<MapEntry<String, String>> rows;
  final double minColumnWidth;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        const gap = 18.0;
        final columns = math.max(1, ((constraints.maxWidth + gap) / (minColumnWidth + gap)).floor());
        final width = (constraints.maxWidth - gap * (columns - 1)) / columns - 0.5;
        return Wrap(
          spacing: gap,
          runSpacing: 10,
          children: [
            for (final row in rows)
              SizedBox(
                width: width,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(row.key, style: const TextStyle(fontSize: TextSizes.tiny, color: Palette.muted)),
                    const SizedBox(height: 2),
                    Text(
                      row.value.isEmpty ? 'Not given' : row.value,
                      style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: Palette.text),
                    ),
                  ],
                ),
              ),
          ],
        );
      },
    );
  }
}

/// A light box with a heading and label-value lines, for the complainant's or the worker's details.
class DetailsBox extends StatelessWidget {
  const DetailsBox({super.key, required this.icon, required this.title, this.rows = const [], this.empty});

  final IconData icon;
  final String title;
  final List<MapEntry<String, String>> rows;

  /// Shown instead of the rows when there are none.
  final String? empty;

  @override
  Widget build(BuildContext context) {
    final phone = isPhone(context);
    final emptyText = empty;
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 12),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: const Color(0xFFF6FAFE),
        border: Border.all(color: Palette.border),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 18, color: Palette.navy),
              const SizedBox(width: 8),
              Text(title, style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w700, color: Palette.navy)),
            ],
          ),
          const SizedBox(height: 8),
          if (rows.isEmpty && emptyText != null)
            Text(emptyText, style: const TextStyle(fontSize: TextSizes.label, color: Palette.muted)),
          for (final row in rows)
            Padding(
              padding: const EdgeInsets.only(bottom: 4),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(
                    width: phone ? 110 : 130,
                    child: Text(row.key, style: const TextStyle(fontSize: 14, color: Palette.muted)),
                  ),
                  Expanded(
                    child: Text(
                      row.value.isEmpty ? 'Not given' : row.value,
                      style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: Palette.text),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

/// A white card for one complaint on a list. [fresh] gives it a light yellow background (a new arrival);
/// [alert] gives it a red edge at the left (a notice).
class JobCard extends StatelessWidget {
  const JobCard({super.key, required this.children, this.fresh = false, this.alert = false});

  final List<Widget> children;
  final bool fresh;
  final bool alert;

  @override
  Widget build(BuildContext context) {
    final phone = isPhone(context);
    final side = phone ? 14.0 : 20.0;
    final card = Container(
      width: double.infinity,
      color: fresh ? const Color(0xFFFFF8E1) : Palette.white,
      padding: EdgeInsets.fromLTRB(side + (alert ? 5 : 0), 16, side, 16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: children),
    );
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: Palette.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Palette.line),
        boxShadow: const [BoxShadow(color: Color(0x0F023668), blurRadius: 8, offset: Offset(0, 2))],
      ),
      // The red edge is drawn over the card, so the card can keep one rounded border of one colour.
      child: Stack(
        children: [
          card,
          if (alert) const Positioned(left: 0, top: 0, bottom: 0, width: 5, child: ColoredBox(color: Palette.error)),
        ],
      ),
    );
  }
}

/// The top line of a complaint card: the ID, what it is, small pills, and a pill at the right side.
class JobTop extends StatelessWidget {
  const JobTop({super.key, required this.id, required this.label, this.pills = const [], this.side});

  final String id;
  final String label;
  final List<Widget> pills;
  final Widget? side;

  @override
  Widget build(BuildContext context) {
    final sidePill = side;
    final left = Wrap(
      spacing: 10,
      runSpacing: 6,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        Text(id, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: Palette.navy)),
        if (label.isNotEmpty)
          Text(label, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: Palette.navy)),
        ...pills,
        if (sidePill != null && isPhone(context)) sidePill,
      ],
    );
    if (sidePill == null || isPhone(context)) return left;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [Expanded(child: left), const SizedBox(width: 12), sidePill],
    );
  }
}

/// The complaint in the citizen's own words, in a light box.
class ComplaintTextBox extends StatelessWidget {
  const ComplaintTextBox(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 12),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: Palette.page,
        border: Border.all(color: Palette.line),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(text, style: const TextStyle(fontSize: 14, color: Palette.text, height: 1.45)),
    );
  }
}

/// A grey dashed-looking box with an icon, for an empty list.
class EmptyBox extends StatelessWidget {
  const EmptyBox({super.key, required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 6),
      padding: const EdgeInsets.all(28),
      decoration: BoxDecoration(
        color: Palette.white,
        border: Border.all(color: Palette.border),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        children: [
          Icon(icon, size: 40, color: Palette.border),
          const SizedBox(height: 8),
          Text(text, textAlign: TextAlign.center, style: const TextStyle(fontSize: TextSizes.label, color: Palette.muted)),
        ],
      ),
    );
  }
}

/// The code a worker asked for, shown to the citizen. This demo shows it on screen instead of sending an SMS.
class CodeForWorkerBox extends StatelessWidget {
  const CodeForWorkerBox({super.key, required this.code, this.minutes});

  final String code;
  final String? minutes;

  @override
  Widget build(BuildContext context) {
    final lasts = minutes == null ? '' : ' It lasts $minutes minutes.';
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(top: 10, bottom: 10),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF8E6),
        border: Border.all(color: const Color(0xFFF3D9A4)),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            crossAxisAlignment: WrapCrossAlignment.center,
            spacing: 8,
            children: [
              const Text('Code for the worker:', style: TextStyle(fontSize: TextSizes.label, color: Palette.warn)),
              SelectableText(
                code,
                style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800, color: Palette.navy, letterSpacing: 5),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            'The worker has finished and asked for this code. Give it to the worker only if the problem is fixed.$lasts',
            style: const TextStyle(fontSize: TextSizes.small, color: Palette.warn),
          ),
        ],
      ),
    );
  }
}

/// A floating message at the bottom of the screen, with an optional button, like the toasts on the web pages.
void showToast(BuildContext context, String message, {String? actionLabel, VoidCallback? onAction}) {
  final messenger = ScaffoldMessenger.maybeOf(context);
  if (messenger == null) return;
  messenger
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Text(message),
        behavior: SnackBarBehavior.floating,
        backgroundColor: Palette.navy,
        width: isPhone(context) ? null : 380,
        duration: const Duration(seconds: 6),
        action: actionLabel == null || onAction == null
            ? null
            : SnackBarAction(label: actionLabel, textColor: Palette.sky, onPressed: onAction),
      ),
    );
}
