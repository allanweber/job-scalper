import 'dart:io';
import 'dart:typed_data';

import 'package:path_provider/path_provider.dart';

// Saves bytes to the device's Downloads directory (Android) or app Documents
// directory (iOS, accessible via the Files app) and returns the full path.
Future<String?> savePdfToDevice(String filename, Uint8List bytes) async {
  Directory? dir = await getDownloadsDirectory();
  dir ??= await getApplicationDocumentsDirectory();
  final path = '${dir.path}/$filename';
  await File(path).writeAsBytes(bytes);
  return path;
}
