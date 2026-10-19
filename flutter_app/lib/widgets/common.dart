import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../config.dart';
import '../theme.dart';
import 'skyline.dart';

/// Keeps content centred, with the page gutter at each side, and no wider than the web pages.
class PageWidth extends StatelessWidget {
  const PageWidth({super.key, required this.child, this.vertical = 0});

  final Widget child;
  final double vertical;

  @override
  Widget build(BuildContext context) {
    // The SizedBox makes the content use the whole page width, so it lines up at the left like the web pages.
    // Without it, a column of short text inside the banner would shrink and sit in the middle.
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: maxPageWidth),
        child: SizedBox(
          width: double.infinity,
          child: Padding(
            padding: EdgeInsets.symmetric(horizontal: pageGutter(context), vertical: vertical),
            child: child,
          ),
        ),
      ),
    );
  }
}

/// One link in a menu.
class NavLink {
  const NavLink(this.label, this.onTap, {this.selected = false, this.icon, this.badge = 0});

  final String label;
  final VoidCallback onTap;
  final bool selected;
  final IconData? icon;

  /// A red count after the words, for example the number of notices. Hidden when 0.
  final int badge;
}

/// The water-drop mark and the app name. It is not any government emblem or portal name.
class BrandMark extends StatelessWidget {
  const BrandMark({super.key, this.tagline = 'Water and sewer complaints for Chennai', this.onTap});

  final String tagline;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final phone = isPhone(context);
    final mark = Container(
      width: phone ? 40 : 46,
      height: phone ? 40 : 46,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(10),
        gradient: const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Palette.primaryBright, Palette.primaryDark],
        ),
      ),
      child: Icon(Icons.water_drop_outlined, color: Palette.white, size: phone ? 22 : 26),
    );
    final words = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          appName,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: phone ? 18 : 24,
            fontWeight: FontWeight.w800,
            color: Palette.navy,
            height: 1.15,
          ),
        ),
        Text(
          tagline,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(fontSize: phone ? 11.5 : 13, color: Palette.labelText),
        ),
      ],
    );
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [mark, const SizedBox(width: 12), Flexible(child: words)],
      ),
    );
  }
}

/// The white bar at the top of every screen: the mark, the menu and, at the right, the account icon.
/// On narrow screens the menu moves to a second row that scrolls sideways.
class PortalTopBar extends StatelessWidget {
  const PortalTopBar({
    super.key,
    this.links = const <NavLink>[],
    this.trailing = const <Widget>[],
    this.iconLinks = false,
    this.tagline = 'Water and sewer complaints for Chennai',
    this.onBrandTap,
  });

  final List<NavLink> links;
  final List<Widget> trailing;

  /// True: links with icons and dividers (sign-up screens). False: text links with an underline (home).
  final bool iconLinks;
  final String tagline;
  final VoidCallback? onBrandTap;

  @override
  Widget build(BuildContext context) {
    final wide = isWideScreen(context);
    final Widget? menu = links.isEmpty
        ? null
        : (iconLinks ? _IconLinks(links: links) : _TextLinks(links: links));
    return Container(
      decoration: const BoxDecoration(
        color: Palette.white,
        border: Border(bottom: BorderSide(color: Palette.line)),
      ),
      child: PageWidth(
        vertical: 10,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: BrandMark(tagline: tagline, onTap: onBrandTap),
                  ),
                ),
                if (wide && menu != null) ...[const SizedBox(width: 24), menu],
                if (trailing.isNotEmpty) ...[const SizedBox(width: 18), ...trailing],
              ],
            ),
            if (!wide && menu != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: SingleChildScrollView(scrollDirection: Axis.horizontal, child: menu),
              ),
          ],
        ),
      ),
    );
  }
}

class _TextLinks extends StatelessWidget {
  const _TextLinks({required this.links});

  final List<NavLink> links;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var i = 0; i < links.length; i++) ...[
          if (i > 0) const SizedBox(width: 22),
          InkWell(
            onTap: links[i].onTap,
            child: Container(
              padding: const EdgeInsets.symmetric(vertical: 6),
              decoration: BoxDecoration(
                border: Border(
                  bottom: BorderSide(
                    color: links[i].selected ? Palette.primary : Colors.transparent,
                    width: 2,
                  ),
                ),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    links[i].label,
                    style: TextStyle(
                      fontSize: 14.5,
                      fontWeight: FontWeight.w600,
                      color: links[i].selected ? Palette.primary : Palette.navy,
                    ),
                  ),
                  if (links[i].badge > 0) ...[
                    const SizedBox(width: 6),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 1),
                      decoration: BoxDecoration(color: Palette.errorBg, borderRadius: BorderRadius.circular(999)),
                      child: Text(
                        '${links[i].badge}',
                        style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Palette.error),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class _IconLinks extends StatelessWidget {
  const _IconLinks({required this.links});

  final List<NavLink> links;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var i = 0; i < links.length; i++) ...[
          if (i > 0) Container(width: 1, height: 26, color: Palette.line),
          InkWell(
            onTap: links[i].onTap,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(links[i].icon ?? Icons.chevron_right, size: 22, color: Palette.primary),
                  const SizedBox(width: 8),
                  Text(
                    links[i].label,
                    style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600, color: Palette.navy),
                  ),
                ],
              ),
            ),
          ),
        ],
      ],
    );
  }
}

/// The blue banner: a gradient with soft clouds, a skyline at the bottom right and, on the home page, a large water drop.
class HeroBanner extends StatelessWidget {
  const HeroBanner({
    super.key,
    required this.child,
    this.compact = false,
    this.showDrop = false,
    this.skylineShare = 0.52,
  });

  final Widget child;
  final bool compact;
  final bool showDrop;

  /// How much of the width the skyline uses on wide screens.
  final double skylineShare;

  @override
  Widget build(BuildContext context) {
    final phone = isPhone(context);
    final width = MediaQuery.sizeOf(context).width;
    final skylineWidth = phone ? width : math.min(width * skylineShare, compact ? 700.0 : 740.0);
    final skylineHeight = phone ? 90.0 : (compact ? 124.0 : 150.0);
    return Container(
      width: double.infinity,
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment(-1, -0.25),
          end: Alignment(1, 0.25),
          colors: [Color(0xFF083B78), Palette.primary, Color(0xFF2A7BC8), Color(0xFF78B6EA)],
          stops: [0, 0.36, 0.64, 1],
        ),
      ),
      child: Stack(
        children: [
          const Positioned.fill(child: _Clouds()),
          if (showDrop && isWideScreen(context))
            Positioned(
              right: width * 0.07,
              top: 30,
              child: const Icon(Icons.water_drop_outlined, size: 210, color: Color(0x73FFFFFF)),
            ),
          Positioned(
            right: 0,
            bottom: 0,
            width: skylineWidth,
            height: skylineHeight,
            child: const Skyline(stroke: Color(0x61FFFFFF), fill: Color(0x1AFFFFFF), strokeWidth: 1.3),
          ),
          PageWidth(
            child: Padding(
              padding: EdgeInsets.only(top: compact ? 30 : 44, bottom: compact ? 28 : 40),
              child: child,
            ),
          ),
        ],
      ),
    );
  }
}

class _Clouds extends StatelessWidget {
  const _Clouds();

  @override
  Widget build(BuildContext context) {
    return const IgnorePointer(
      child: Stack(
        children: [
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: RadialGradient(
                  center: Alignment(0.64, -0.56),
                  radius: 0.9,
                  colors: [Color(0x47FFFFFF), Color(0x00FFFFFF)],
                ),
              ),
            ),
          ),
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: RadialGradient(
                  center: Alignment(0.24, -0.8),
                  radius: 0.6,
                  colors: [Color(0x29FFFFFF), Color(0x00FFFFFF)],
                ),
              ),
            ),
          ),
          Positioned.fill(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: RadialGradient(
                  center: Alignment(0.92, 0.2),
                  radius: 0.8,
                  colors: [Color(0x2EFFFFFF), Color(0x00FFFFFF)],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// The two-line headline, with one part in sky blue: "Clean Water, Clear Drains / for Every Street in Chennai".
class HeroHeadline extends StatelessWidget {
  const HeroHeadline({
    super.key,
    this.compact = false,
    this.line1 = 'Clean Water, Clear Drains',
    this.before = 'for Every Street in ',
    this.sky = 'Chennai',
    this.after = '',
  });

  final bool compact;
  final String line1;
  final String before;
  final String sky;
  final String after;

  @override
  Widget build(BuildContext context) {
    final phone = isPhone(context);
    final size = phone ? TextSizes.headlinePhone : (compact ? TextSizes.headlineCompact : TextSizes.headline);
    return Text.rich(
      TextSpan(
        style: TextStyle(
          color: Palette.white,
          fontSize: size,
          fontWeight: FontWeight.w800,
          height: 1.1,
          letterSpacing: -0.3,
        ),
        children: [
          if (line1.isNotEmpty) TextSpan(text: phone ? '$line1 ' : '$line1\n'),
          TextSpan(text: before),
          TextSpan(text: sky, style: const TextStyle(color: Palette.sky)),
          TextSpan(text: after),
        ],
      ),
    );
  }
}

/// The sentence under the headline.
class HeroLead extends StatelessWidget {
  const HeroLead(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 16),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 580),
        child: Text(
          text,
          style: TextStyle(
            color: Palette.bannerSub,
            fontSize: isPhone(context) ? TextSizes.leadPhone : TextSizes.lead,
            height: 1.5,
          ),
        ),
      ),
    );
  }
}

/// The small icons with words along the bottom of the banner.
class FeatureChips extends StatelessWidget {
  const FeatureChips({
    super.key,
    this.labels = const <String>['Clean water', 'Clear drains', 'Quick response', 'Your voice matters'],
  });

  final List<String> labels;

  static const List<IconData> _icons = <IconData>[
    Icons.water_drop_outlined,
    Icons.plumbing,
    Icons.bolt,
    Icons.campaign_outlined,
  ];

  @override
  Widget build(BuildContext context) {
    final count = math.min(labels.length, _icons.length);
    return Padding(
      padding: const EdgeInsets.only(top: 24),
      child: Wrap(
        spacing: 26,
        runSpacing: 12,
        children: [
          for (var i = 0; i < count; i++)
            Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(_icons[i], color: Palette.white, size: 20),
                const SizedBox(width: 8),
                Text(labels[i], style: const TextStyle(color: Palette.white, fontSize: 13.5)),
              ],
            ),
        ],
      ),
    );
  }
}

/// The blue strip of links under the banner on the sign-up screens.
class NavStrip extends StatelessWidget {
  const NavStrip({super.key, required this.links});

  final List<NavLink> links;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Palette.primary,
      child: PageWidth(
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: [
              for (final link in links)
                Padding(
                  padding: const EdgeInsets.only(right: 30),
                  child: InkWell(
                    onTap: link.onTap,
                    child: Container(
                      padding: const EdgeInsets.fromLTRB(0, 13, 18, 13),
                      decoration: BoxDecoration(
                        border: Border(
                          bottom: BorderSide(
                            color: link.selected ? Palette.sky : Colors.transparent,
                            width: 3,
                          ),
                        ),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(link.icon ?? Icons.chevron_right, color: Palette.white, size: 20),
                          const SizedBox(width: 10),
                          Text(
                            link.label,
                            style: TextStyle(
                              color: Palette.white,
                              fontSize: TextSizes.body,
                              fontWeight: link.selected ? FontWeight.w700 : FontWeight.w500,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// "Fields marked with * are mandatory", shown at the right of a form's title band.
class MandatoryNote extends StatelessWidget {
  const MandatoryNote({super.key});

  @override
  Widget build(BuildContext context) {
    return const Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(Icons.person, size: 26, color: Palette.navy),
        SizedBox(width: 10),
        Flexible(
          child: Text.rich(
            TextSpan(
              style: TextStyle(fontSize: 13.5, color: Palette.labelText),
              children: [
                TextSpan(text: 'Fields marked with '),
                TextSpan(text: '*', style: TextStyle(color: Palette.requiredStar)),
                TextSpan(text: ' are mandatory'),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

/// A white card with a light blue title band, in the style of the reference sign-up screen.
class FormCard extends StatelessWidget {
  const FormCard({
    super.key,
    required this.icon,
    required this.title,
    required this.child,
    this.subtitle,
    this.showMandatory = true,
    this.headTrailing,
    this.footer,
  });

  final IconData icon;
  final String title;
  final String? subtitle;
  final bool showMandatory;
  final Widget? headTrailing;
  final Widget child;
  final Widget? footer;

  @override
  Widget build(BuildContext context) {
    final phone = isPhone(context);
    final side = phone ? 16.0 : 28.0;
    final titleBlock = Row(
      children: [
        Icon(icon, size: phone ? 40 : 52, color: Palette.navy),
        SizedBox(width: phone ? 12 : 18),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                title,
                style: TextStyle(
                  fontSize: phone ? TextSizes.formTitlePhone : TextSizes.formTitle,
                  fontWeight: FontWeight.w800,
                  color: Palette.navy,
                ),
              ),
              if (subtitle != null)
                Text(subtitle!, style: const TextStyle(fontSize: TextSizes.body, color: Palette.labelText)),
            ],
          ),
        ),
      ],
    );
    final Widget? note = headTrailing ?? (showMandatory ? const MandatoryNote() : null);
    final Widget head;
    if (note == null) {
      head = titleBlock;
    } else if (phone) {
      head = Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [titleBlock, const SizedBox(height: 10), note],
      );
    } else {
      head = Row(children: [Expanded(child: titleBlock), const SizedBox(width: 16), Flexible(child: note)]);
    }
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 24),
      clipBehavior: Clip.antiAlias,
      decoration: BoxDecoration(
        color: Palette.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFFCFE0F0)),
        boxShadow: const [BoxShadow(color: Color(0x12023668), blurRadius: 10, offset: Offset(0, 2))],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            color: Palette.sectionBg,
            padding: EdgeInsets.symmetric(horizontal: side, vertical: phone ? 14 : 18),
            child: head,
          ),
          Padding(padding: EdgeInsets.fromLTRB(side, 18, side, 22), child: child),
          if (footer != null) Padding(padding: EdgeInsets.fromLTRB(side, 0, side, 18), child: footer),
        ],
      ),
    );
  }
}

/// Two columns with a line between them on wide screens; one column on narrow ones.
class TwoColumns extends StatelessWidget {
  const TwoColumns({super.key, required this.left, required this.right});

  final List<Widget> left;
  final List<Widget> right;

  @override
  Widget build(BuildContext context) {
    if (!isWideScreen(context)) {
      return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [...left, ...right]);
    }
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: left)),
        const SizedBox(width: 28),
        Expanded(
          child: Container(
            padding: const EdgeInsets.only(left: 28),
            decoration: const BoxDecoration(border: Border(left: BorderSide(color: Palette.line))),
            child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: right),
          ),
        ),
      ],
    );
  }
}

/// A field label with a red star when the field is required.
class FieldLabel extends StatelessWidget {
  const FieldLabel(this.text, {super.key, this.required = false});

  final String text;
  final bool required;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 5),
      child: Text.rich(
        TextSpan(
          style: const TextStyle(fontSize: TextSizes.label, fontWeight: FontWeight.w600, color: Palette.labelText),
          children: [
            TextSpan(text: text),
            if (required) const TextSpan(text: ' *', style: TextStyle(color: Palette.requiredStar)),
          ],
        ),
      ),
    );
  }
}

/// A label, the field, an optional hint under it, and space below.
class LabeledField extends StatelessWidget {
  const LabeledField({
    super.key,
    required this.label,
    required this.child,
    this.required = false,
    this.hint,
  });

  final String label;
  final Widget child;
  final bool required;
  final String? hint;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          FieldLabel(label, required: required),
          child,
          if (hint != null)
            Padding(
              padding: const EdgeInsets.only(top: 5),
              child: Text(hint!, style: const TextStyle(fontSize: TextSizes.tiny, color: Palette.muted)),
            ),
        ],
      ),
    );
  }
}

/// The look of a text field, with an optional icon inside at the left.
InputDecoration fieldDecoration({String? hint, IconData? icon}) {
  return InputDecoration(
    hintText: hint,
    prefixIcon: icon == null ? null : Icon(icon, size: 18, color: Palette.navy),
  );
}

/// A drop-down that looks like the text fields. It is disabled when [onChanged] is null.
class PortalDropdown<T> extends StatelessWidget {
  const PortalDropdown({
    super.key,
    required this.value,
    required this.items,
    required this.onChanged,
    required this.hint,
    this.disabledHint,
  });

  final T? value;
  final List<DropdownMenuItem<T>> items;
  final ValueChanged<T?>? onChanged;
  final String hint;
  final String? disabledHint;

  @override
  Widget build(BuildContext context) {
    const hintStyle = TextStyle(fontSize: TextSizes.label, color: Palette.placeholder);
    return InputDecorator(
      decoration: InputDecoration(
        enabled: onChanged != null,
        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
        fillColor: onChanged == null ? Palette.readOnlyFill : Palette.inputFill,
      ),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<T>(
          value: value,
          isExpanded: true,
          hint: Text(hint, style: hintStyle),
          disabledHint: Text(disabledHint ?? hint, style: hintStyle),
          items: items,
          onChanged: onChanged,
          style: const TextStyle(fontSize: TextSizes.label, color: Palette.text),
          icon: const Icon(Icons.keyboard_arrow_down, color: Palette.navy),
        ),
      ),
    );
  }
}

/// A grey box that looks like a field and shows a value that cannot be changed.
class ReadOnlyBox extends StatelessWidget {
  const ReadOnlyBox({super.key, required this.value});

  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
      decoration: BoxDecoration(
        color: Palette.readOnlyFill,
        border: Border.all(color: Palette.inputBorder),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(
        value.isEmpty ? '-' : value,
        style: const TextStyle(fontSize: TextSizes.label, color: Palette.labelText),
      ),
    );
  }
}

enum NoticeTone { ok, error, info }

/// A message in a coloured box: green for good news, red for errors, blue for information.
class NoticeBox extends StatelessWidget {
  const NoticeBox({super.key, required this.text, this.tone = NoticeTone.ok});

  final String text;
  final NoticeTone tone;

  @override
  Widget build(BuildContext context) {
    var background = Palette.sectionBg;
    var edge = Palette.line;
    var colour = Palette.labelText;
    switch (tone) {
      case NoticeTone.ok:
        background = Palette.successBg;
        edge = const Color(0xFFB7DCC3);
        colour = Palette.success;
        break;
      case NoticeTone.error:
        background = Palette.errorBg;
        edge = const Color(0xFFF0C3BF);
        colour = Palette.error;
        break;
      case NoticeTone.info:
        background = Palette.sectionBg;
        edge = Palette.line;
        colour = Palette.labelText;
        break;
    }
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: background,
        border: Border.all(color: edge),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(text, style: TextStyle(color: colour, fontSize: TextSizes.label)),
    );
  }
}

/// Red error text under a form.
class ErrorText extends StatelessWidget {
  const ErrorText(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Text(
        text,
        style: const TextStyle(color: Palette.error, fontWeight: FontWeight.w600, fontSize: TextSizes.label),
      ),
    );
  }
}

enum ButtonKind { primary, outline, danger, light, onBlue }

/// The buttons used everywhere. [kind] picks the colours; light and onBlue are for the blue banner.
class PortalButton extends StatelessWidget {
  const PortalButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.icon,
    this.trailingIcon,
    this.kind = ButtonKind.primary,
    this.busy = false,
    this.expand = false,
    this.small = false,
  });

  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;
  final IconData? trailingIcon;
  final ButtonKind kind;
  final bool busy;
  final bool expand;
  final bool small;

  @override
  Widget build(BuildContext context) {
    var background = Palette.primary;
    var foreground = Palette.white;
    var edge = Palette.primary;
    switch (kind) {
      case ButtonKind.primary:
        background = Palette.primary;
        foreground = Palette.white;
        edge = Palette.primary;
        break;
      case ButtonKind.outline:
        background = Palette.white;
        foreground = Palette.primary;
        edge = Palette.primary;
        break;
      case ButtonKind.danger:
        background = Palette.white;
        foreground = Palette.error;
        edge = Palette.error;
        break;
      case ButtonKind.light:
        background = Palette.white;
        foreground = Palette.navy;
        edge = Palette.white;
        break;
      case ButtonKind.onBlue:
        background = Colors.transparent;
        foreground = Palette.white;
        edge = const Color(0xD9FFFFFF);
        break;
    }
    final Widget content = busy
        ? SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2, color: foreground))
        : Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (icon != null) ...[Icon(icon, size: 18), const SizedBox(width: 8)],
              Text(label),
              if (trailingIcon != null) ...[const SizedBox(width: 8), Icon(trailingIcon, size: 18)],
            ],
          );
    final button = TextButton(
      onPressed: busy ? null : onPressed,
      style: TextButton.styleFrom(
        backgroundColor: background,
        foregroundColor: foreground,
        disabledBackgroundColor: background.withAlpha(170),
        disabledForegroundColor: foreground,
        minimumSize: Size(0, small ? 36 : 44),
        padding: EdgeInsets.symmetric(horizontal: small ? 12 : 20),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(6),
          side: BorderSide(color: edge),
        ),
        textStyle: TextStyle(fontSize: small ? 14 : TextSizes.button, fontWeight: FontWeight.w600),
      ),
      child: content,
    );
    return expand ? SizedBox(width: double.infinity, child: button) : button;
  }
}

/// A heading for a part of a page, with a line under it and an optional link at the right.
class SectionHead extends StatelessWidget {
  const SectionHead({super.key, required this.title, this.subtitle, this.trailing});

  final String title;
  final String? subtitle;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final words = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(
          title,
          style: const TextStyle(fontSize: TextSizes.sectionTitle, fontWeight: FontWeight.w800, color: Palette.navy),
        ),
        if (subtitle != null)
          Padding(
            padding: const EdgeInsets.only(top: 2),
            child: Text(subtitle!, style: const TextStyle(fontSize: TextSizes.label, color: Palette.muted)),
          ),
      ],
    );
    final Widget? extra = trailing;
    if (extra == null) return words;
    if (isPhone(context)) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [words, const SizedBox(height: 8), extra],
      );
    }
    return Row(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [Expanded(child: words), const SizedBox(width: 12), Flexible(child: extra)],
    );
  }
}

/// One number on a numbers strip.
class StatData {
  const StatData(this.icon, this.tone, this.value, this.label);

  final IconData icon;
  final Tone tone;
  final int value;
  final String label;
}

/// The light blue strip of numbers ("Your Complaints in Numbers").
class NumbersStrip extends StatelessWidget {
  const NumbersStrip({super.key, required this.title, required this.subtitle, required this.stats});

  final String title;
  final String subtitle;
  final List<StatData> stats;

  Widget _stat(StatData stat) {
    return Row(
      children: [
        Container(
          width: 40,
          height: 40,
          decoration: const BoxDecoration(color: Palette.white, shape: BoxShape.circle),
          child: Icon(stat.icon, size: 20, color: stat.tone.foreground),
        ),
        const SizedBox(width: 12),
        Flexible(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                '${stat.value}',
                style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w700, color: Palette.navy, height: 1.1),
              ),
              Text(stat.label, style: const TextStyle(fontSize: TextSizes.tiny, color: Palette.muted)),
            ],
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final titleBlock = Row(
      children: [
        const Icon(Icons.bar_chart, size: 30, color: Palette.primary),
        const SizedBox(width: 12),
        Flexible(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(title, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w700, color: Palette.navy)),
              Text(subtitle, style: const TextStyle(fontSize: TextSizes.tiny, color: Palette.muted)),
            ],
          ),
        ),
      ],
    );
    final Widget body;
    if (width >= 1100) {
      body = Row(
        children: [
          Expanded(flex: 17, child: titleBlock),
          for (final stat in stats)
            Expanded(
              flex: 10,
              child: Container(
                padding: const EdgeInsets.only(left: 16),
                decoration: const BoxDecoration(border: Border(left: BorderSide(color: Palette.cardEdge))),
                child: _stat(stat),
              ),
            ),
        ],
      );
    } else {
      final rows = <Widget>[];
      for (var i = 0; i < stats.length; i += 2) {
        rows.add(Padding(
          padding: const EdgeInsets.only(top: 14),
          child: Row(
            children: [
              Expanded(child: _stat(stats[i])),
              const SizedBox(width: 12),
              Expanded(child: i + 1 < stats.length ? _stat(stats[i + 1]) : const SizedBox.shrink()),
            ],
          ),
        ));
      }
      body = Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [titleBlock, ...rows]);
    }
    return Container(
      padding: EdgeInsets.symmetric(horizontal: isPhone(context) ? 14 : 22, vertical: 16),
      decoration: BoxDecoration(
        color: Palette.sectionBg,
        border: Border.all(color: Palette.cardEdge),
        borderRadius: BorderRadius.circular(12),
      ),
      child: body,
    );
  }
}

/// A small rounded label, for example a status.
class Pill extends StatelessWidget {
  const Pill(this.text, {super.key, required this.background, required this.foreground});

  final String text;
  final Color background;
  final Color foreground;

  /// The status of a complaint, with the words a citizen or an officer should see.
  factory Pill.status(String status, {bool forOfficer = false}) {
    switch (status) {
      case 'open':
        return Pill(forOfficer ? 'Open' : 'In progress',
            background: const Color(0xFFDDEEFF), foreground: const Color(0xFF0A56A8));
      case 'awaiting_confirmation':
        return Pill(forOfficer ? 'Waiting for citizen' : 'Waiting for you',
            background: Palette.warnBg, foreground: Palette.warn);
      case 'closed':
        return const Pill('Closed', background: Palette.successBg, foreground: Palette.success);
      default:
        return Pill(status, background: Palette.sectionBg, foreground: Palette.labelText);
    }
  }

  factory Pill.overdue([String text = 'Time limit passed']) =>
      Pill(text, background: Palette.errorBg, foreground: Palette.error);

  factory Pill.newItem() => const Pill('New', background: Palette.primaryBright, foreground: Palette.white);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
      decoration: BoxDecoration(color: background, borderRadius: BorderRadius.circular(999)),
      child: Text(text, style: TextStyle(fontSize: TextSizes.tiny, fontWeight: FontWeight.w600, color: foreground)),
    );
  }
}

/// A green dot that pulses, with words such as "Live". Grey and still when [paused].
class LiveIndicator extends StatefulWidget {
  const LiveIndicator({super.key, required this.text, this.paused = false});

  final String text;
  final bool paused;

  @override
  State<LiveIndicator> createState() => _LiveIndicatorState();
}

class _LiveIndicatorState extends State<LiveIndicator> with SingleTickerProviderStateMixin {
  late final AnimationController _pulse;

  @override
  void initState() {
    super.initState();
    _pulse = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
      lowerBound: 0.35,
      upperBound: 1,
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final dot = Container(
      width: 9,
      height: 9,
      decoration: BoxDecoration(
        color: widget.paused ? const Color(0xFFC1C9D4) : Palette.live,
        shape: BoxShape.circle,
      ),
    );
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        widget.paused ? dot : FadeTransition(opacity: _pulse, child: dot),
        const SizedBox(width: 8),
        Text(widget.text, style: const TextStyle(fontSize: TextSizes.small, color: Palette.muted)),
      ],
    );
  }
}

/// A white panel with a border and a soft shadow.
class Panel extends StatelessWidget {
  const Panel({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final phone = isPhone(context);
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.symmetric(vertical: 18),
      padding: EdgeInsets.symmetric(horizontal: phone ? 14 : 22, vertical: phone ? 14 : 18),
      decoration: BoxDecoration(
        color: Palette.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Palette.line),
        boxShadow: const [BoxShadow(color: Color(0x12023668), blurRadius: 10, offset: Offset(0, 2))],
      ),
      child: child,
    );
  }
}

/// The blue footer. It says the app is not affiliated with CMWSSB.
class PortalFooter extends StatelessWidget {
  const PortalFooter({super.key});

  static const String madeBy = 'Made by Abhinav Reddy and Tony Madhuri. Not affiliated with CMWSSB.';

  @override
  Widget build(BuildContext context) {
    const style = TextStyle(color: Palette.white, fontSize: 13.5);
    const skyline = SizedBox(
      width: 260,
      height: 44,
      child: Skyline(stroke: Color(0xD9FFFFFF), strokeWidth: 1.2),
    );
    final demo = Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(width: 26, height: 1, color: const Color(0xCCFFFFFF)),
        const SizedBox(width: 10),
        const Text('Unofficial demo', style: style),
        const SizedBox(width: 10),
        Container(width: 26, height: 1, color: const Color(0xCCFFFFFF)),
      ],
    );
    return Container(
      color: Palette.primary,
      child: PageWidth(
        vertical: 10,
        child: isWideScreen(context)
            ? Row(
                children: [
                  const Expanded(child: Text(madeBy, style: style)),
                  const SizedBox(width: 16),
                  skyline,
                  const SizedBox(width: 16),
                  Expanded(child: Align(alignment: Alignment.centerRight, child: demo)),
                ],
              )
            : Column(
                children: [
                  const Text(madeBy, style: style, textAlign: TextAlign.center),
                  const SizedBox(height: 6),
                  skyline,
                  const SizedBox(height: 6),
                  demo,
                ],
              ),
      ),
    );
  }
}

const List<String> _months = <String>['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/// Turns a date from the server (UTC) into this device's time, for example "22 Oct 2026, 10:49 pm".
String formatWhen(String? iso, {String empty = 'No time limit'}) {
  if (iso == null || iso.isEmpty) return empty;
  final parsed = DateTime.tryParse(iso);
  if (parsed == null) return iso;
  final local = parsed.toLocal();
  final hour12 = local.hour % 12 == 0 ? 12 : local.hour % 12;
  final minute = local.minute.toString().padLeft(2, '0');
  final half = local.hour < 12 ? 'am' : 'pm';
  final day = local.day.toString().padLeft(2, '0');
  return '$day ${_months[local.month - 1]} ${local.year}, $hour12:$minute $half';
}

/// The time now as hours, minutes and seconds, for "updated 10:49:37 pm".
String formatClock(DateTime time) {
  final hour12 = time.hour % 12 == 0 ? 12 : time.hour % 12;
  String two(int value) => value.toString().padLeft(2, '0');
  return '$hour12:${two(time.minute)}:${two(time.second)} ${time.hour < 12 ? 'am' : 'pm'}';
}
