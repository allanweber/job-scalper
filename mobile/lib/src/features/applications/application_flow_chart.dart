import 'package:flutter/material.dart';

import '../../data/models/draft_models.dart';
import '../../theme/tokens.dart';
import 'application_status.dart';

/// A Sankey-style flow chart of the user's application funnel, à la rabbit
/// resume: a single "Applications" source flows out to where each application
/// currently sits (Applied / Pre-Screen / Interviewing / Ghosted / Rejected),
/// and the interviewing band flows on to Offer.
///
/// Layout is computed from [insights] alone (width-independent), so the widget
/// sizes itself; the painter only maps the columns across the available width.
class ApplicationFlowChart extends StatelessWidget {
  const ApplicationFlowChart({super.key, required this.insights});

  final ApplicationInsights insights;

  // Vertical scale reference: the source bar maps to this many logical pixels;
  // every band/node is proportional to it. Tuned so a busy funnel reads well on
  // a phone without scrolling.
  static const double _baseHeight = 260;
  static const double _topPad = 22;
  static const double _botPad = 10;
  static const double _minSlot = 22; // vertical room a node reserves for a label
  static const double _minBar = 2.5; // thinnest a 1-count node bar can get
  static const double _gap = 8;

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final scheme = Theme.of(context).colorScheme;
    final layout = _layout(dark);

    if (insights.total == 0 || layout.nodes.isEmpty) {
      return const SizedBox.shrink();
    }

    return SizedBox(
      height: layout.height,
      child: CustomPaint(
        size: Size.infinite,
        painter: _SankeyPainter(
          layout: layout,
          labelColor: scheme.onSurface,
          subLabelColor: scheme.onSurfaceVariant,
        ),
      ),
    );
  }

  _FlowLayout _layout(bool dark) {
    final c = insights.counts;
    int v(String s) => c[s] ?? 0;
    final total = insights.total;
    if (total <= 0) return const _FlowLayout(nodes: [], links: [], height: 0);
    final scale = _baseHeight / total;

    // Column 1 buckets, top → bottom. Interviewing carries everyone who reached
    // an interview (interviewing + offer), then branches to Offer in column 2.
    final interviewingThroughput = v('interviewing') + v('offer');
    final col1 = <({String id, int value})>[
      if (v('applied') > 0) (id: 'applied', value: v('applied')),
      if (v('pre_screen') > 0) (id: 'pre_screen', value: v('pre_screen')),
      if (interviewingThroughput > 0)
        (id: 'interviewing', value: interviewingThroughput),
      if (v('ghosted') > 0) (id: 'ghosted', value: v('ghosted')),
      if (v('rejected') > 0) (id: 'rejected', value: v('rejected')),
    ];

    double barOf(int value) =>
        (value * scale).clamp(_minBar, double.infinity).toDouble();

    // Stack column 1 by slots (so thin bars still get label room), and remember
    // each node's bar rect.
    final nodes = <_FlowNode>[];
    double cursor = _topPad;
    _FlowNode? interviewing;
    for (final n in col1) {
      final barH = barOf(n.value);
      final slot = barH < _minSlot ? _minSlot : barH;
      final top = cursor + (slot - barH) / 2;
      final node = _FlowNode(
        id: n.id,
        label: applicationStageLabel(n.id),
        value: n.value,
        column: 1,
        top: top,
        height: barH,
        barColor: _barColor(n.id, dark),
        bandColor: _bandColor(n.id, dark),
      );
      nodes.add(node);
      if (n.id == 'interviewing') interviewing = node;
      cursor += slot + _gap;
    }
    final col1Bottom = cursor - _gap;

    // Column 2: Offer, aligned to the interviewing band it flows from.
    final links = <_FlowLink>[for (final n in col1) _FlowLink('apps', n.id, n.value)];
    if (v('offer') > 0 && interviewing != null) {
      final barH = barOf(v('offer'));
      final top =
          interviewing.top + interviewing.height / 2 - barH / 2;
      nodes.add(_FlowNode(
        id: 'offer',
        label: applicationStageLabel('offer'),
        value: v('offer'),
        column: 2,
        top: top,
        height: barH,
        barColor: _barColor('offer', dark),
        bandColor: _bandColor('offer', dark),
      ));
      links.add(_FlowLink('interviewing', 'offer', v('offer')));
    }

    // The source bar spans the proportional height, centered against the spread
    // of column 1 so bands fan out symmetrically.
    final sourceH = total * scale;
    final spread = col1Bottom - _topPad;
    final sourceTop = _topPad + (spread - sourceH) / 2;
    nodes.insert(
      0,
      _FlowNode(
        id: 'apps',
        label: 'Applications',
        value: total,
        column: 0,
        top: sourceTop < _topPad ? _topPad : sourceTop,
        height: sourceH,
        barColor: AppTokens.brandPrimary,
        bandColor: (dark ? AppTokens.brandPrimaryContainerDark
                : AppTokens.brandPrimaryContainerLight)
            .withValues(alpha: dark ? 0.55 : 0.85),
      ),
    );

    final maxCol = nodes.fold(0, (m, n) => n.column > m ? n.column : m);
    final height = col1Bottom + _botPad;
    return _FlowLayout(nodes: nodes, links: links, height: height, columns: maxCol + 1);
  }

  Color _barColor(String stage, bool dark) => applicationStageColors(stage, dark).fg;

  Color _bandColor(String stage, bool dark) => applicationStageColors(stage, dark)
      .bg
      .withValues(alpha: dark ? 0.5 : 0.8);
}

class _FlowNode {
  const _FlowNode({
    required this.id,
    required this.label,
    required this.value,
    required this.column,
    required this.top,
    required this.height,
    required this.barColor,
    required this.bandColor,
  });

  final String id;
  final String label;
  final int value;
  final int column;
  final double top;
  final double height;
  final Color barColor;
  final Color bandColor;

  double get bottom => top + height;
}

class _FlowLink {
  const _FlowLink(this.from, this.to, this.value);
  final String from;
  final String to;
  final int value;
}

class _FlowLayout {
  const _FlowLayout({
    required this.nodes,
    required this.links,
    required this.height,
    this.columns = 1,
  });
  final List<_FlowNode> nodes;
  final List<_FlowLink> links;
  final double height;
  final int columns;
}

class _SankeyPainter extends CustomPainter {
  _SankeyPainter({
    required this.layout,
    required this.labelColor,
    required this.subLabelColor,
  });

  final _FlowLayout layout;
  final Color labelColor;
  final Color subLabelColor;

  static const double _nodeW = 11;
  static const double _leftLabelW = 74;
  static const double _rightLabelW = 116;

  @override
  void paint(Canvas canvas, Size size) {
    final byId = {for (final n in layout.nodes) n.id: n};
    final cols = layout.columns;
    final spanW = size.width - _leftLabelW - _rightLabelW - _nodeW;

    double colX(int c) =>
        cols <= 1 ? _leftLabelW : _leftLabelW + spanW * (c / (cols - 1));

    // Sub-segment cursors so a node with several outgoing/incoming links packs
    // its bands along its edge in link order.
    final outCursor = <String, double>{};
    final inCursor = <String, double>{};

    for (final link in layout.links) {
      final from = byId[link.from];
      final to = byId[link.to];
      if (from == null || to == null) continue;
      final segH = (link.value / from.value) * from.height;
      final oy = outCursor[from.id] ?? from.top;
      final iy = inCursor[to.id] ?? to.top;
      outCursor[from.id] = oy + segH;
      // Incoming spans the full target bar (single inbound here), so pin to top.
      inCursor[to.id] = iy + to.height;

      final x0 = colX(from.column) + _nodeW;
      final x1 = colX(to.column);
      final midX = (x0 + x1) / 2;
      final path = Path()
        ..moveTo(x0, oy)
        ..cubicTo(midX, oy, midX, iy, x1, iy)
        ..lineTo(x1, iy + to.height)
        ..cubicTo(midX, iy + to.height, midX, oy + segH, x0, oy + segH)
        ..close();
      canvas.drawPath(path, Paint()..color = to.bandColor);
    }

    // Nodes (drawn over the bands) + labels.
    for (final n in layout.nodes) {
      final x = colX(n.column);
      final rect = RRect.fromRectAndRadius(
        Rect.fromLTWH(x, n.top, _nodeW, n.height),
        const Radius.circular(3),
      );
      canvas.drawRRect(rect, Paint()..color = n.barColor);
      _paintLabel(canvas, n, x);
    }
  }

  void _paintLabel(Canvas canvas, _FlowNode n, double x) {
    final tp = TextPainter(
      text: TextSpan(children: [
        TextSpan(
            text: n.label,
            style: TextStyle(
                fontSize: 11.5,
                fontWeight: FontWeight.w700,
                color: labelColor)),
        TextSpan(
            text: '  ${n.value}',
            style: TextStyle(
                fontSize: 11.5,
                fontWeight: FontWeight.w700,
                color: subLabelColor)),
      ]),
      textDirection: TextDirection.ltr,
      maxLines: 1,
      ellipsis: '…',
    );

    if (n.column == 0) {
      // Source: label to the left of the bar, vertically centered.
      tp.layout(maxWidth: _leftLabelW - 6);
      tp.paint(canvas, Offset(x - 6 - tp.width, n.top + n.height / 2 - tp.height / 2));
    } else {
      // Right columns: label to the right of the bar, centered on it.
      tp.layout(maxWidth: _rightLabelW - 6);
      tp.paint(
          canvas, Offset(x + _nodeW + 6, n.top + n.height / 2 - tp.height / 2));
    }
  }

  @override
  bool shouldRepaint(_SankeyPainter old) =>
      old.layout != layout ||
      old.labelColor != labelColor ||
      old.subLabelColor != subLabelColor;
}
