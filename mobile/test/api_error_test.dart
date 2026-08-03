import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:job_scalper/src/util/api_error.dart';

DioException _dio({int? status, Object? data, DioExceptionType type = DioExceptionType.badResponse}) {
  final req = RequestOptions(path: '/x');
  return DioException(
    requestOptions: req,
    type: type,
    response: status == null
        ? null
        : Response(requestOptions: req, statusCode: status, data: data),
  );
}

void main() {
  test('surfaces the backend detail string instead of Dio\'s dump', () {
    final e = _dio(status: 402, data: {
      'detail': 'monthly draft limit reached (20/20); add a personal LLM key '
          'or wait for reset',
    });
    final msg = apiErrorMessage(e);
    expect(msg, startsWith('monthly draft limit reached'));
    expect(msg, isNot(contains('DioException')));
  });

  test('falls back to a friendly network message on connection errors', () {
    final e = _dio(type: DioExceptionType.connectionError);
    expect(apiErrorMessage(e), contains('Check your connection'));
  });

  test('reports the status code when there is no detail body', () {
    final e = _dio(status: 500, data: 'oops');
    expect(apiErrorMessage(e), contains('500'));
  });

  test('strips the "Exception:" prefix from plain thrown errors', () {
    expect(apiErrorMessage(Exception('boom')), 'boom');
  });
}
