import 'dart:math' as math;

import 'package:flutter/material.dart';

/// A made-up city skyline (plain blocks, a dome, a clock tower, a temple tower and a lighthouse).
/// The same drawing as portal/assets/icons.svg#skyline on the web pages. It is drawn in a 600 x 90 box.
class SkylinePainter extends CustomPainter {
  const SkylinePainter({
    required this.stroke,
    this.fill,
    this.strokeWidth = 1.2,
    this.repeat = false,
  });

  final Color stroke;
  final Color? fill;
  final double strokeWidth;

  /// True: the drawing is repeated across the whole width at full height (the band at the bottom of the first screen).
  /// False: one drawing, as large as fits, at the bottom centre.
  final bool repeat;

  static const double _boxWidth = 600;
  static const double _boxHeight = 90;

  // Each list is one line: x, y, x, y, ...
  static const List<List<double>> _lines = <List<double>>[
    <double>[0, 88, 0, 60, 30, 60, 30, 88],
    <double>[32, 88, 32, 48, 54, 48, 54, 88],
    <double>[56, 88, 56, 66, 82, 66, 82, 88],
    <double>[84, 88, 84, 38, 102, 38, 102, 88],
    <double>[104, 88, 104, 58, 154, 58, 154, 88],
    <double>[129, 36, 129, 28],
    <double>[160, 88, 160, 30, 176, 30, 176, 88],
    <double>[158, 30, 168, 12, 178, 30],
    <double>[180, 88, 180, 62, 220, 62, 220, 88],
    <double>[222, 88, 222, 50, 246, 50, 246, 88],
    <double>[250, 88, 250, 22, 268, 22, 268, 88],
    <double>[270, 88, 270, 34, 290, 34, 290, 88],
    <double>[292, 88, 292, 56, 322, 56, 322, 88],
    <double>[330, 88, 334, 50, 356, 50, 360, 88],
    <double>[336, 50, 339, 36, 351, 36, 354, 50],
    <double>[341, 36, 343, 26, 347, 26, 349, 36],
    <double>[366, 88, 366, 60, 400, 60, 400, 88],
    <double>[402, 88, 402, 44, 422, 44, 422, 88],
    <double>[424, 88, 424, 64, 464, 64, 464, 88],
    <double>[476, 88, 480, 40, 488, 40, 492, 88],
    <double>[478, 40, 478, 32, 490, 32, 490, 40],
    <double>[478, 32, 484, 24, 490, 32],
    <double>[500, 88, 500, 56, 526, 56, 526, 88],
    <double>[528, 88, 528, 46, 546, 46, 546, 88],
    <double>[548, 88, 548, 62, 600, 62, 600, 88],
    <double>[0, 88, 600, 88],
  ];

  @override
  void paint(Canvas canvas, Size size) {
    if (size.width <= 0 || size.height <= 0) return;
    if (repeat) {
      final scale = size.height / _boxHeight;
      final tile = _boxWidth * scale;
      var x = ((size.width % tile) / 2) - tile;
      while (x < size.width) {
        _drawOne(canvas, Offset(x, 0), scale);
        x += tile;
      }
      return;
    }
    final scale = math.min(size.width / _boxWidth, size.height / _boxHeight);
    final dx = (size.width - _boxWidth * scale) / 2;
    final dy = size.height - _boxHeight * scale;
    _drawOne(canvas, Offset(dx, dy), scale);
  }

  void _drawOne(Canvas canvas, Offset origin, double scale) {
    canvas.save();
    canvas.translate(origin.dx, origin.dy);
    canvas.scale(scale);
    final strokePaint = Paint()
      ..color = stroke
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth / scale
      ..strokeJoin = StrokeJoin.round;
    final fillColor = fill;
    final fillPaint = fillColor == null
        ? null
        : (Paint()
          ..color = fillColor
          ..style = PaintingStyle.fill);

    for (final points in _lines) {
      final path = Path()..moveTo(points[0], points[1]);
      for (var i = 2; i + 1 < points.length; i += 2) {
        path.lineTo(points[i], points[i + 1]);
      }
      if (fillPaint != null && points.length > 4) {
        final closed = Path.from(path)..close();
        canvas.drawPath(closed, fillPaint);
      }
      canvas.drawPath(path, strokePaint);
    }

    final dome = Path()
      ..moveTo(110, 58)
      ..quadraticBezierTo(129, 30, 148, 58);
    if (fillPaint != null) {
      final closedDome = Path.from(dome)..close();
      canvas.drawPath(closedDome, fillPaint);
    }
    canvas.drawPath(dome, strokePaint);
    if (fillPaint != null) canvas.drawCircle(const Offset(168, 40), 4, fillPaint);
    canvas.drawCircle(const Offset(168, 40), 4, strokePaint);
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant SkylinePainter oldDelegate) {
    return oldDelegate.stroke != stroke ||
        oldDelegate.fill != fill ||
        oldDelegate.strokeWidth != strokeWidth ||
        oldDelegate.repeat != repeat;
  }
}

/// The skyline as a widget. Give it a size from outside, for example with a SizedBox or Positioned.
class Skyline extends StatelessWidget {
  const Skyline({
    super.key,
    required this.stroke,
    this.fill,
    this.strokeWidth = 1.2,
    this.repeat = false,
  });

  final Color stroke;
  final Color? fill;
  final double strokeWidth;
  final bool repeat;

  @override
  Widget build(BuildContext context) {
    return CustomPaint(
      size: Size.infinite,
      painter: SkylinePainter(stroke: stroke, fill: fill, strokeWidth: strokeWidth, repeat: repeat),
    );
  }
}
