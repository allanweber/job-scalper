import 'package:dio/dio.dart';

import '../config/env.dart';

/// Supplies/refreshes the bearer token for the API client.
///
/// The session controller implements this so the client can read the current
/// access token and transparently refresh it on a 401 without a circular import.
abstract class TokenStore {
  String? get accessToken;
  String? get refreshToken;

  /// Persist a freshly rotated token pair (called after a successful refresh).
  Future<void> onTokensRefreshed(String access, String refresh);

  /// Clear the session (called when refresh fails / the user is signed out).
  Future<void> onAuthLost();
}

/// A thin Dio wrapper: base URL, JSON, bearer injection, and single-flight
/// refresh-on-401 against `POST /auth/refresh`.
class ApiClient {
  ApiClient(this._tokens, {Dio? dio})
      : _dio = dio ??
            Dio(BaseOptions(
              baseUrl: Env.apiBaseUrl,
              connectTimeout: const Duration(seconds: 20),
              receiveTimeout: const Duration(seconds: 30),
              headers: {'Content-Type': 'application/json'},
            )) {
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) {
        final t = _tokens.accessToken;
        if (t != null && options.extra['noAuth'] != true) {
          options.headers['Authorization'] = 'Bearer $t';
        }
        handler.next(options);
      },
      onError: _onError,
    ));
  }

  final Dio _dio;
  final TokenStore _tokens;
  Future<bool>? _refreshing;

  Dio get raw => _dio;

  Future<void> _onError(DioException e, ErrorInterceptorHandler handler) async {
    final res = e.response;
    final isRetry = e.requestOptions.extra['retried'] == true;
    final refreshable = res?.statusCode == 401 &&
        _tokens.refreshToken != null &&
        e.requestOptions.extra['noAuth'] != true &&
        !isRetry;
    if (!refreshable) return handler.next(e);

    final ok = await (_refreshing ??= _refresh());
    _refreshing = null;
    if (!ok) {
      await _tokens.onAuthLost();
      return handler.next(e);
    }
    try {
      final opts = e.requestOptions
        ..extra['retried'] = true
        ..headers['Authorization'] = 'Bearer ${_tokens.accessToken}';
      final clone = await _dio.fetch(opts);
      return handler.resolve(clone);
    } on DioException catch (err) {
      return handler.next(err);
    }
  }

  Future<bool> _refresh() async {
    try {
      final r = await _dio.post('/auth/refresh',
          data: {'refresh_token': _tokens.refreshToken},
          options: Options(extra: {'noAuth': true}));
      final data = r.data as Map<String, dynamic>;
      await _tokens.onTokensRefreshed(
          data['access_token'] as String, data['refresh_token'] as String);
      return true;
    } on DioException {
      return false;
    }
  }

  // -- verbs (thin passthroughs; repositories add typing) --
  Future<Response<T>> get<T>(String path, {Map<String, dynamic>? query}) =>
      _dio.get<T>(path, queryParameters: query);

  Future<Response<T>> post<T>(String path,
          {Object? data, bool noAuth = false}) =>
      _dio.post<T>(path, data: data, options: Options(extra: {'noAuth': noAuth}));

  Future<Response<T>> put<T>(String path, {Object? data}) =>
      _dio.put<T>(path, data: data);

  Future<Response<T>> delete<T>(String path) => _dio.delete<T>(path);
}
