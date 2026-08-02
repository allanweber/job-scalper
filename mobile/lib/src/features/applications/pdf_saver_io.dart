import 'dart:io';
import 'dart:typed_data';

import 'package:path_provider/path_provider.dart';

// Saves bytes to the app's documents directory — no special permissions needed.
// On iOS the file is accessible via Files app → On My iPhone → [app name].
// On Android it's in the app's private data dir (no permission required).
Future<String?> savePdfToDevice(String filename, Uint8List bytes) async {
  final dir = await getApplicationDocumentsDirectory();
  final path = '${dir.path}/$filename';
  await File(path).writeAsBytes(bytes);
  return path;
}
