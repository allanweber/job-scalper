import 'dart:typed_data';

import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;

/// Renders a draft document's markdown to a print-ready PDF **on the device**
/// (the backend deliberately doesn't render PDFs at runtime). It's a light
/// markdown pass — headings, bullets, and paragraphs — which is all the
/// resume/cover-letter drafts use.
Future<Uint8List> buildDraftPdf({
  required String title,
  required String markdown,
}) async {
  final doc = pw.Document(title: title);
  final widgets = _blocks(markdown);

  doc.addPage(
    pw.MultiPage(
      pageFormat: PdfPageFormat.letter,
      margin: const pw.EdgeInsets.symmetric(horizontal: 54, vertical: 48),
      build: (_) => widgets,
    ),
  );
  return doc.save();
}

List<pw.Widget> _blocks(String markdown) {
  final out = <pw.Widget>[];
  final lines = markdown.replaceAll('\r\n', '\n').split('\n');

  for (var raw in lines) {
    final line = _clean(raw.trimRight());
    if (line.trim().isEmpty) {
      out.add(pw.SizedBox(height: 8));
      continue;
    }
    if (line.startsWith('### ')) {
      out.add(_heading(line.substring(4), 13));
    } else if (line.startsWith('## ')) {
      out.add(_heading(line.substring(3), 15));
    } else if (line.startsWith('# ')) {
      out.add(pw.Padding(
        padding: const pw.EdgeInsets.only(bottom: 2),
        child: pw.Text(line.substring(2),
            style: pw.TextStyle(fontSize: 22, fontWeight: pw.FontWeight.bold)),
      ));
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      out.add(_bullet(line.substring(2)));
    } else {
      out.add(pw.Paragraph(
        text: line,
        margin: const pw.EdgeInsets.only(bottom: 4),
        style: const pw.TextStyle(fontSize: 11, lineSpacing: 2),
      ));
    }
  }
  return out;
}

pw.Widget _heading(String text, double size) => pw.Padding(
      padding: const pw.EdgeInsets.only(top: 10, bottom: 4),
      child: pw.Text(text,
          style: pw.TextStyle(fontSize: size, fontWeight: pw.FontWeight.bold)),
    );

pw.Widget _bullet(String text) => pw.Padding(
      padding: const pw.EdgeInsets.only(left: 8, bottom: 3),
      child: pw.Row(
        crossAxisAlignment: pw.CrossAxisAlignment.start,
        children: [
          pw.Text('•  ', style: const pw.TextStyle(fontSize: 11)),
          pw.Expanded(
            child: pw.Text(text,
                style: const pw.TextStyle(fontSize: 11, lineSpacing: 2)),
          ),
        ],
      ),
    );

/// The built-in Helvetica is Latin-1; strip markdown emphasis markers and map
/// common typographic punctuation to ASCII so no glyph is missing.
String _clean(String s) => s
    .replaceAll('**', '')
    .replaceAll('–', '-')
    .replaceAll('—', '-')
    .replaceAll('·', '-')
    .replaceAll('“', '"')
    .replaceAll('”', '"')
    .replaceAll('‘', "'")
    .replaceAll('’', "'");
