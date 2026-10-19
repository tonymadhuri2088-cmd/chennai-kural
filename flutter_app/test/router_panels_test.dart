// Tests for the router's message and timeline panels. Run with `flutter test`.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:chennai_complaints/widgets/router_panels.dart';

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: SingleChildScrollView(child: child)));

void main() {
  testWidgets('the router message shows its banner as a notice and the rest as the message', (tester) async {
    await tester.pumpWidget(
      _wrap(const RouterMessage(message: 'DRAFT - NOT AN OFFICIAL REPLY\n\nComplaint reference: CMP-20261018-0001\nForwarded to: Depot')),
    );
    expect(find.text('DRAFT - NOT AN OFFICIAL REPLY'), findsOneWidget);
    expect(find.textContaining('Complaint reference: CMP-20261018-0001'), findsOneWidget);
    expect(find.textContaining('Forwarded to: Depot'), findsOneWidget);
  });

  testWidgets('a missing router message says so instead of showing nothing', (tester) async {
    await tester.pumpWidget(_wrap(const RouterMessage(message: null)));
    expect(find.text('The router sent no message for this complaint.'), findsOneWidget);
  });

  testWidgets('the router timeline shows each office, its time limit and where the complaint is now', (tester) async {
    const progress = <String, dynamic>{
      'label': 'Water leakage in a pipe (service line)',
      'repair_time': '3 days',
      'steps': [
        {'stage': 'depot', 'office': 'Depot Engineer', 'time_limit': '3 days', 'state': 'done'},
        {
          'stage': 'deputy_ae',
          'office': 'Deputy Area Engineer',
          'time_limit': '2 days',
          'state': 'current',
          'deadline': '2026-10-22T05:19:00+00:00',
        },
        {'stage': 'district_head', 'office': 'District Head Office', 'time_limit': 'Final level. No time limit', 'state': 'upcoming'},
      ],
      'after_last_level': 'If not solved, a notification goes to the Chief Engineer.',
      'note': 'The charter does not state whether these days are cumulative.',
    };
    await tester.pumpWidget(_wrap(const RouterProgress(progress: progress)));
    expect(find.textContaining('charter repair time 3 days'), findsOneWidget);
    expect(find.text('Depot Engineer'), findsOneWidget);
    expect(find.text('Time limit: 2 days'), findsOneWidget);
    expect(find.text('Done'), findsOneWidget);
    expect(find.text('Now'), findsOneWidget);
    expect(find.text('Next'), findsOneWidget);
    expect(find.textContaining('Counting down to'), findsOneWidget);
  });

  testWidgets('no router timeline means nothing is drawn', (tester) async {
    await tester.pumpWidget(_wrap(const RouterProgress(progress: null)));
    expect(find.textContaining('Time limit'), findsNothing);
    expect(find.textContaining('charter repair time'), findsNothing);
  });
}
