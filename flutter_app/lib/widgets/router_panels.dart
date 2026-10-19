import 'package:flutter/material.dart';

import '../theme.dart';
import 'common.dart';

/// The router's message for the citizen, exactly as the router wrote it.
/// Its first line is a banner saying the text is a draft and not an official reply. It is shown as a notice,
/// and the rest of the text is shown as the message.
class RouterMessage extends StatelessWidget {
  const RouterMessage({super.key, required this.message});

  final String? message;

  @override
  Widget build(BuildContext context) {
    final text = message ?? '';
    if (text.isEmpty) {
      return const Text(
        'The router sent no message for this complaint.',
        style: TextStyle(fontSize: TextSizes.label, color: Palette.muted),
      );
    }
    final cut = text.indexOf('\n\n');
    final banner = cut == -1 ? '' : text.substring(0, cut);
    final body = cut == -1 ? text : text.substring(cut + 2);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (banner.isNotEmpty)
          Container(
            width: double.infinity,
            margin: const EdgeInsets.only(bottom: 10),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(color: Palette.warnBg, borderRadius: BorderRadius.circular(8)),
            child: Text(
              banner,
              style: const TextStyle(fontSize: TextSizes.tiny, fontWeight: FontWeight.w700, color: Palette.warn),
            ),
          ),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: Palette.white,
            border: Border.all(color: Palette.line),
            borderRadius: BorderRadius.circular(10),
          ),
          child: SelectableText(
            body,
            style: const TextStyle(fontSize: TextSizes.label, height: 1.5, color: Palette.text),
          ),
        ),
      ],
    );
  }
}

/// The router's timeline as steps: each office, its time limit, and where the complaint is now.
/// `progress` is the `router_progress` object the server sends with a complaint.
class RouterProgress extends StatelessWidget {
  const RouterProgress({super.key, required this.progress});

  final Object? progress;

  @override
  Widget build(BuildContext context) {
    final data = progress;
    if (data is! Map) return const SizedBox.shrink();
    final steps = data['steps'];
    if (steps is! List || steps.isEmpty) return const SizedBox.shrink();
    final label = data['label']?.toString() ?? '';
    final repair = data['repair_time']?.toString() ?? '';
    final after = data['after_last_level']?.toString() ?? '';
    final note = data['note']?.toString() ?? '';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (label.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Text(
              repair.isEmpty ? label : '$label - charter repair time $repair',
              style: const TextStyle(fontSize: TextSizes.label, fontWeight: FontWeight.w700, color: Palette.labelText),
            ),
          ),
        for (final raw in steps.whereType<Map>()) _step(raw),
        if (after.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(after, style: const TextStyle(fontSize: TextSizes.small, color: Palette.muted)),
          ),
        if (note.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 6, bottom: 8),
            child: Text(note, style: const TextStyle(fontSize: TextSizes.small, color: Palette.muted)),
          ),
      ],
    );
  }

  Widget _step(Map step) {
    final state = step['state']?.toString() ?? '';
    final deadline = step['deadline']?.toString() ?? '';
    final words = <String, String>{'done': 'Done', 'current': 'Now', 'upcoming': 'Next', 'skipped': 'Not needed'};
    final isDone = state == 'done';
    final isCurrent = state == 'current';
    final accent = isDone ? Palette.success : (isCurrent ? Palette.primaryBright : Palette.border);
    final mark = isDone ? '\u2713' : (isCurrent ? '\u25CF' : (state == 'skipped' ? '\u2013' : ''));
    return Opacity(
      opacity: state == 'skipped' ? 0.6 : 1,
      child: Container(
        width: double.infinity,
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: isCurrent ? const Color(0xFFF1F8FF) : Palette.white,
          border: Border.all(color: isCurrent ? Palette.primaryBright : Palette.line),
          borderRadius: BorderRadius.circular(10),
        ),
        child: Row(
          children: [
            Container(
              width: 24,
              height: 24,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: state == 'upcoming' ? Palette.white : accent,
                border: Border.all(color: accent, width: 2),
              ),
              child: Text(mark, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: Palette.white)),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    step['office']?.toString() ?? '',
                    style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w600, color: Palette.navy),
                  ),
                  Text(
                    'Time limit: ${step['time_limit'] ?? ''}',
                    style: const TextStyle(fontSize: TextSizes.small, color: Palette.muted),
                  ),
                  if (deadline.isNotEmpty)
                    Text(
                      'Counting down to ${formatWhen(deadline)}',
                      style: const TextStyle(fontSize: TextSizes.small, fontWeight: FontWeight.w600, color: Palette.primary),
                    ),
                ],
              ),
            ),
            const SizedBox(width: 8),
            Text(
              words[state] ?? '',
              style: TextStyle(
                fontSize: TextSizes.tiny,
                fontWeight: FontWeight.w700,
                color: isDone ? Palette.success : (isCurrent ? Palette.primary : Palette.muted),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
