import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../theme/tokens.dart';

/// A circular match-score indicator: a colored arc proportional to the 0–100
/// score with the number in the centre. Color follows the shared score bands
/// so a score reads the same here, in detail, and in the saved list.
class ScoreRing extends StatelessWidget {
  const ScoreRing({super.key, required this.score, this.size = 52});

  final int score;
  final double size;

  @override
  Widget build(BuildContext context) {
    final color = AppTokens.scoreColor(score);
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(
        painter: _RingPainter(
          score: score,
          color: color,
          track: color.withValues(alpha: 0.16),
        ),
        child: Center(
          child: Text(
            '$score',
            style: TextStyle(
              fontFamily: 'RobotoMono',
              fontSize: size * 0.32,
              fontWeight: FontWeight.w700,
              color: color,
            ),
          ),
        ),
      ),
    );
  }
}

class _RingPainter extends CustomPainter {
  _RingPainter({required this.score, required this.color, required this.track});

  final int score;
  final Color color;
  final Color track;

  @override
  void paint(Canvas canvas, Size size) {
    final stroke = size.width * 0.11;
    final rect = Offset(stroke / 2, stroke / 2) &
        Size(size.width - stroke, size.height - stroke);
    final trackPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke
      ..color = track;
    final arcPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = stroke
      ..strokeCap = StrokeCap.round
      ..color = color;

    canvas.drawArc(rect, 0, 2 * math.pi, false, trackPaint);
    final sweep = 2 * math.pi * (score.clamp(0, 100) / 100);
    canvas.drawArc(rect, -math.pi / 2, sweep, false, arcPaint);
  }

  @override
  bool shouldRepaint(_RingPainter old) =>
      old.score != score || old.color != color || old.track != track;
}
