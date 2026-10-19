// This file also stops `flutter create .` from adding its default counter-app test, which would not compile here.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:chennai_complaints/widgets/board.dart';
import 'package:chennai_complaints/widgets/common.dart';

void main() {
  testWidgets('status pills use the words a citizen and an officer should see', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Column(
            children: [
              Pill.status('open'),
              Pill.status('awaiting_confirmation', forOfficer: true),
            ],
          ),
        ),
      ),
    );
    expect(find.text('In progress'), findsOneWidget);
    expect(find.text('Waiting for citizen'), findsOneWidget);
  });

  testWidgets('a citizen sees a green Resolved, or Allotted while a worker has the complaint', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Column(
            children: [
              StatusPill.forCitizen(const <String, dynamic>{'status': 'closed'}),
              StatusPill.forCitizen(const <String, dynamic>{'status': 'open', 'work_status': 'allotted'}),
              StatusPill.forCitizen(const <String, dynamic>{'status': 'open'}),
            ],
          ),
        ),
      ),
    );
    expect(find.textContaining('Resolved'), findsOneWidget); // the tick sits in the same text
    expect(find.byIcon(Icons.check), findsOneWidget);
    expect(find.text('Allotted · Work in progress'), findsOneWidget);
    expect(find.text('Registered'), findsOneWidget);
  });

  test('dates from the server are shown with the month name', () {
    expect(formatWhen('2026-10-22T05:19:00+00:00'), contains('Oct 2026'));
    expect(formatWhen(null), 'No time limit');
  });
}
