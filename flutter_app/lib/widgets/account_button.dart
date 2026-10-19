import 'package:flutter/material.dart';

import '../theme.dart';

/// The round account icon. Tapping it shows the account's details and the only Log out button.
class AccountButton extends StatelessWidget {
  const AccountButton({
    super.key,
    required this.name,
    required this.details,
    required this.onLogout,
  });

  final String name;
  final List<MapEntry<String, String>> details;
  final Future<void> Function() onLogout;

  String get _initials {
    final words = name.trim().split(RegExp(r'\s+')).where((word) => word.isNotEmpty).toList();
    if (words.isEmpty) return '?';
    if (words.length == 1) return words.first.substring(0, 1).toUpperCase();
    return (words.first.substring(0, 1) + words[1].substring(0, 1)).toUpperCase();
  }

  void _open(BuildContext context) {
    showDialog<void>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        backgroundColor: Palette.white,
        surfaceTintColor: Palette.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        title: const Text(
          'Your details',
          style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700, color: Palette.navy),
        ),
        content: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 320),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (final row in details)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SizedBox(
                        width: 78,
                        child: Text(row.key, style: const TextStyle(fontSize: TextSizes.label, color: Palette.muted)),
                      ),
                      Expanded(
                        child: Text(
                          row.value.isEmpty ? 'Not recorded' : row.value,
                          style: const TextStyle(
                            fontSize: TextSizes.label,
                            fontWeight: FontWeight.w600,
                            color: Palette.text,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('Close'),
          ),
          OutlinedButton.icon(
            onPressed: () async {
              Navigator.of(dialogContext).pop();
              await onLogout();
            },
            icon: const Icon(Icons.logout, size: 18),
            label: const Text('Log out'),
            style: OutlinedButton.styleFrom(
              foregroundColor: Palette.primary,
              side: const BorderSide(color: Palette.primary),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: 'Your account',
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: () => _open(context),
        child: Container(
          width: 44,
          height: 44,
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: Palette.primary,
            shape: BoxShape.circle,
            border: Border.all(color: Palette.white, width: 2),
            boxShadow: const [BoxShadow(color: Palette.primary, spreadRadius: 2)],
          ),
          child: Text(
            _initials,
            style: const TextStyle(color: Palette.white, fontWeight: FontWeight.w700, fontSize: 15),
          ),
        ),
      ),
    );
  }
}

/// The citizen's details for the account icon.
List<MapEntry<String, String>> citizenDetails(Map<String, dynamic> profile) {
  String text(String key) => profile[key]?.toString() ?? '';
  return [
    MapEntry('Name', text('name')),
    MapEntry('Mobile', text('mobile')),
    MapEntry('Address', text('address')),
    MapEntry('Zone', text('zone')),
    MapEntry('Ward', text('ward')),
  ];
}
