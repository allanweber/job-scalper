import 'dart:typed_data';

import 'package:path/path.dart';
import 'package:sqflite/sqflite.dart';

/// Caches rendered PDF bytes on-device keyed by (draftId, docType).
///
/// Invalidated when the user edits a draft — call [invalidate] after a
/// successful PUT so the next download re-fetches from the PDF service.
class PdfCacheRepository {
  Database? _db;

  Future<Database> get _database async {
    _db ??= await _open();
    return _db!;
  }

  Future<Database> _open() async {
    final path = join(await getDatabasesPath(), 'pdf_cache.db');
    return openDatabase(path, version: 1, onCreate: (db, _) {
      return db.execute(
        'CREATE TABLE pdf_cache('
        '  draft_id TEXT NOT NULL,'
        '  doc_type TEXT NOT NULL,'
        '  bytes BLOB NOT NULL,'
        '  PRIMARY KEY (draft_id, doc_type)'
        ')',
      );
    });
  }

  Future<Uint8List?> get(String draftId, String docType) async {
    final db = await _database;
    final rows = await db.query(
      'pdf_cache',
      columns: ['bytes'],
      where: 'draft_id = ? AND doc_type = ?',
      whereArgs: [draftId, docType],
    );
    if (rows.isEmpty) return null;
    final raw = rows.first['bytes'];
    if (raw is List<int>) return Uint8List.fromList(raw);
    return null;
  }

  Future<void> put(String draftId, String docType, Uint8List bytes) async {
    final db = await _database;
    await db.insert(
      'pdf_cache',
      {'draft_id': draftId, 'doc_type': docType, 'bytes': bytes},
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<void> invalidate(String draftId) async {
    final db = await _database;
    await db.delete('pdf_cache',
        where: 'draft_id = ?', whereArgs: [draftId]);
  }

  /// Drop every cached PDF. Called on account deletion so no rendered resume or
  /// cover letter is left on the device.
  Future<void> clear() async {
    final db = await _database;
    await db.delete('pdf_cache');
  }
}
