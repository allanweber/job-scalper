import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/account_models.dart';
import '../../data/providers.dart';

@immutable
class LlmKeyState {
  const LlmKeyState({
    this.loading = true,
    this.busyProvider,
    this.keys = const LlmKeysInfo(),
    this.error,
  });

  final bool loading;

  /// The provider whose key is currently being saved/removed, if any.
  final String? busyProvider;
  final LlmKeysInfo keys;
  final String? error;

  LlmKeyState copyWith({
    bool? loading,
    Object? busyProvider = _sentinel,
    LlmKeysInfo? keys,
    Object? error = _sentinel,
  }) =>
      LlmKeyState(
        loading: loading ?? this.loading,
        busyProvider:
            busyProvider == _sentinel ? this.busyProvider : busyProvider as String?,
        keys: keys ?? this.keys,
        error: error == _sentinel ? this.error : error as String?,
      );

  static const _sentinel = Object();
}

/// Backs the BYO LLM key screen. Keys are write-only server-side, so state only
/// reflects whether a key is on file per provider and whether it validated.
class LlmKeyController extends Notifier<LlmKeyState> {
  @override
  LlmKeyState build() {
    _load();
    return const LlmKeyState();
  }

  Future<void> _load() async {
    try {
      final keys = await ref.read(accountRepositoryProvider).getKeys();
      state = state.copyWith(loading: false, keys: keys);
    } catch (e) {
      state = state.copyWith(loading: false, error: '$e');
    }
  }

  Future<bool> save(String provider, String apiKey) async {
    state = state.copyWith(busyProvider: provider, error: null);
    try {
      final keys =
          await ref.read(accountRepositoryProvider).putKey(provider, apiKey);
      state = state.copyWith(busyProvider: null, keys: keys);
      return true;
    } on DioException catch (e) {
      state = state.copyWith(busyProvider: null, error: _message(e));
      return false;
    } catch (e) {
      state = state.copyWith(busyProvider: null, error: '$e');
      return false;
    }
  }

  Future<void> remove(String provider) async {
    state = state.copyWith(busyProvider: provider, error: null);
    try {
      final keys = await ref.read(accountRepositoryProvider).deleteKey(provider);
      state = state.copyWith(busyProvider: null, keys: keys);
    } on DioException catch (e) {
      state = state.copyWith(busyProvider: null, error: _message(e));
    } catch (e) {
      state = state.copyWith(busyProvider: null, error: '$e');
    }
  }

  String _message(DioException e) {
    final data = e.response?.data;
    if (data is Map && data['detail'] is String) return data['detail'] as String;
    if (e.response?.statusCode == 503) {
      return 'Your own keys aren\'t available right now. Try again later.';
    }
    return 'Could not save that key. Check it and try again.';
  }
}

final llmKeyControllerProvider =
    NotifierProvider.autoDispose<LlmKeyController, LlmKeyState>(
        LlmKeyController.new);
