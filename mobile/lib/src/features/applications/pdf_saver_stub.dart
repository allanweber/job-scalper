import 'dart:typed_data';

// Fallback for platforms where dart:io is unavailable (web).
Future<String?> savePdfToDevice(String filename, Uint8List bytes) async => null;
