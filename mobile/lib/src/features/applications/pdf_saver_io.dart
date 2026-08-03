import 'dart:io';
import 'dart:typed_data';

import 'package:open_file/open_file.dart';
import 'package:path_provider/path_provider.dart';

Future<String?> savePdfToDevice(String filename, Uint8List bytes) async {
  final dir = await getApplicationDocumentsDirectory();
  final path = '${dir.path}/$filename';
  await File(path).writeAsBytes(bytes);
  await OpenFile.open(path);
  return path;
}
