import 'package:dio/dio.dart';

/// Turns any thrown error into a short, user-facing message.
///
/// For API failures this surfaces the backend's `detail` string — e.g. the
/// quota "monthly draft limit reached (…); add a personal LLM key or wait for
/// reset" message on a 402 — instead of Dio's internal multi-line exception
/// dump. Connection/timeout errors get a friendly network message; anything
/// else falls back to [fallback] (or a "Exception:"-stripped message).
String apiErrorMessage(
  Object e, {
  String fallback = 'Something went wrong. Please try again.',
}) {
  if (e is DioException) {
    final detail = e.response?.data;
    if (detail is Map &&
        detail['detail'] is String &&
        (detail['detail'] as String).trim().isNotEmpty) {
      return (detail['detail'] as String).trim();
    }
    switch (e.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
      case DioExceptionType.connectionError:
        return "Can't reach the server. Check your connection and try again.";
      default:
        final code = e.response?.statusCode;
        return code == null ? fallback : 'Request failed ($code). Please try again.';
    }
  }
  final s = e.toString();
  if (s.startsWith('Exception: ')) return s.substring(11);
  return s.isEmpty ? fallback : s;
}
