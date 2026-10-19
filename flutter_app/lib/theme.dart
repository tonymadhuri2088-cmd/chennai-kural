import 'package:flutter/material.dart';

/// Colours from the web pages (portal/assets/portal.css), which were sampled from the reference screenshots.
class Palette {
  Palette._();

  static const Color primary = Color(0xFF0557A3);
  static const Color primaryDark = Color(0xFF014582);
  static const Color primaryBright = Color(0xFF066DD1);
  static const Color navy = Color(0xFF023668);
  static const Color labelText = Color(0xFF123C6E);
  static const Color text = Color(0xFF1C3557);
  static const Color muted = Color(0xFF5A729E);
  static const Color placeholder = Color(0xFF7F8B9B);
  static const Color sky = Color(0xFF98D1F9);
  static const Color bannerSub = Color(0xFFE3F1FF);
  static const Color page = Color(0xFFF8FCFF);
  static const Color sectionBg = Color(0xFFE7F4FD);
  static const Color inputFill = Color(0xFFF7FBFE);
  static const Color readOnlyFill = Color(0xFFEEF4FA);
  static const Color border = Color(0xFFB3C5D9);
  static const Color inputBorder = Color(0xFFC9D8E8);
  static const Color line = Color(0xFFD6E4F2);
  static const Color cardEdge = Color(0xFFCFE3F6);
  static const Color white = Color(0xFFFFFFFF);
  static const Color success = Color(0xFF1E7B34);
  static const Color successBg = Color(0xFFEAF6EE);
  static const Color error = Color(0xFFB3261E);
  static const Color errorBg = Color(0xFFFCEDEC);
  static const Color warn = Color(0xFF7A4A00);
  static const Color warnBg = Color(0xFFFFF4E0);
  static const Color requiredStar = Color(0xFFD1242F);
  static const Color skyband = Color(0xFF9CC3EA);
  static const Color live = Color(0xFF23B45A);
}

/// A soft colour behind an icon, and the icon's colour. Used on the service cards, numbers and steps.
class Tone {
  const Tone(this.background, this.foreground);

  final Color background;
  final Color foreground;

  static const Tone blue = Tone(Color(0xFFDDEEFF), Color(0xFF0A64C2));
  static const Tone purple = Tone(Color(0xFFECE6FF), Color(0xFF6A46C9));
  static const Tone orange = Tone(Color(0xFFFFE9DC), Color(0xFFD4561A));
  static const Tone yellow = Tone(Color(0xFFFFF3C9), Color(0xFFA77700));
  static const Tone green = Tone(Color(0xFFDCF3E3), Color(0xFF1F8A43));
  static const Tone teal = Tone(Color(0xFFD8F2F2), Color(0xFF0F8585));
}

/// Text sizes in logical pixels, the same as the web pages.
class TextSizes {
  TextSizes._();

  static const double headline = 48;
  static const double headlineCompact = 40;
  static const double headlinePhone = 30;
  static const double lead = 18;
  static const double leadPhone = 15.5;
  static const double formTitle = 28;
  static const double formTitlePhone = 22;
  static const double sectionTitle = 24;
  static const double body = 15;
  static const double label = 14;
  static const double small = 13;
  static const double tiny = 12.5;
  static const double button = 15;
}

/// Wide screens (laptops, tablets on their side) show two columns and the login card beside the banner.
bool isWideScreen(BuildContext context) => MediaQuery.sizeOf(context).width >= 960;

/// Phones: one column, smaller headline.
bool isPhone(BuildContext context) => MediaQuery.sizeOf(context).width < 640;

/// The space at the left and right of the page.
double pageGutter(BuildContext context) {
  final width = MediaQuery.sizeOf(context).width;
  if (width < 640) return 16;
  if (width < 960) return 20;
  return 40;
}

/// The page content is never wider than this, like the web pages.
const double maxPageWidth = 1320;

ThemeData buildTheme() {
  final scheme = ColorScheme.fromSeed(seedColor: Palette.primary).copyWith(
    primary: Palette.primary,
    surface: Palette.page,
  );
  OutlineInputBorder outline(Color color, [double width = 1]) => OutlineInputBorder(
        borderRadius: BorderRadius.circular(6),
        borderSide: BorderSide(color: color, width: width),
      );
  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    scaffoldBackgroundColor: Palette.page,
    textTheme: ThemeData.light().textTheme.apply(bodyColor: Palette.text, displayColor: Palette.navy),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: Palette.inputFill,
      isDense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 13),
      hintStyle: const TextStyle(color: Palette.placeholder, fontSize: TextSizes.label),
      border: outline(Palette.inputBorder),
      enabledBorder: outline(Palette.inputBorder),
      focusedBorder: outline(Palette.primaryBright, 1.5),
      errorBorder: outline(Palette.error),
      focusedErrorBorder: outline(Palette.error, 1.5),
    ),
  );
}
