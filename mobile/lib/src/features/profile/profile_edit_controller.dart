import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/account_models.dart';
import '../../data/providers.dart';

@immutable
class ProfileEditState {
  const ProfileEditState({
    this.loading = true,
    this.saving = false,
    this.original = const Profile(),
    this.working = const Profile(),
    this.error,
    this.saved = false,
  });

  final bool loading;
  final bool saving;

  /// The last-persisted profile; [working] is the in-progress edit.
  final Profile original;
  final Profile working;
  final String? error;
  final bool saved;

  /// True once the user has changed anything from the persisted profile.
  bool get dirty => working.toFields().toString() != original.toFields().toString();

  ProfileEditState copyWith({
    bool? loading,
    bool? saving,
    Profile? original,
    Profile? working,
    Object? error = _sentinel,
    bool? saved,
  }) =>
      ProfileEditState(
        loading: loading ?? this.loading,
        saving: saving ?? this.saving,
        original: original ?? this.original,
        working: working ?? this.working,
        error: error == _sentinel ? this.error : error as String?,
        saved: saved ?? this.saved,
      );

  static const _sentinel = Object();
}

/// Loads the user's match profile and tracks edits against it. A missing
/// profile (404) is treated as an empty starting point rather than an error.
class ProfileEditController extends Notifier<ProfileEditState> {
  @override
  ProfileEditState build() {
    _load();
    return const ProfileEditState();
  }

  Future<void> _load() async {
    try {
      final p = await ref.read(accountRepositoryProvider).getProfile();
      state = state.copyWith(loading: false, original: p, working: p);
    } on DioException catch (e) {
      if (e.response?.statusCode == 404) {
        // No profile yet — start from a blank, editable form.
        state = state.copyWith(loading: false);
      } else {
        state = state.copyWith(loading: false, error: _message(e));
      }
    } catch (e) {
      state = state.copyWith(loading: false, error: '$e');
    }
  }

  void update(Profile working) =>
      state = state.copyWith(working: working, error: null);

  Future<bool> save() async {
    state = state.copyWith(saving: true, error: null);
    try {
      final saved = await ref.read(accountRepositoryProvider).saveProfile(state.working);
      state = state.copyWith(
          saving: false, original: saved, working: saved, saved: true);
      return true;
    } on DioException catch (e) {
      state = state.copyWith(saving: false, error: _message(e));
      return false;
    } catch (e) {
      state = state.copyWith(saving: false, error: '$e');
      return false;
    }
  }

  String _message(DioException e) {
    final data = e.response?.data;
    if (data is Map && data['detail'] is String) return data['detail'] as String;
    return 'Could not save your profile. Check your connection and try again.';
  }
}

final profileEditControllerProvider =
    NotifierProvider.autoDispose<ProfileEditController, ProfileEditState>(
        ProfileEditController.new);
