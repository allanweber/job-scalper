import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models/account_models.dart';
import '../../data/providers.dart';

enum RebuildPhase { idle, running, done, failed }

@immutable
class ResumeState {
  const ResumeState({
    this.loading = true,
    this.uploading = false,
    this.resume,
    this.error,
    this.rebuild = RebuildPhase.idle,
    this.rebuildError,
  });

  final bool loading;
  final bool uploading;
  final ResumeInfo? resume;
  final String? error;
  final RebuildPhase rebuild;
  final String? rebuildError;

  bool get hasResume => resume != null;

  ResumeState copyWith({
    bool? loading,
    bool? uploading,
    Object? resume = _sentinel,
    Object? error = _sentinel,
    RebuildPhase? rebuild,
    Object? rebuildError = _sentinel,
  }) =>
      ResumeState(
        loading: loading ?? this.loading,
        uploading: uploading ?? this.uploading,
        resume: resume == _sentinel ? this.resume : resume as ResumeInfo?,
        error: error == _sentinel ? this.error : error as String?,
        rebuild: rebuild ?? this.rebuild,
        rebuildError: rebuildError == _sentinel
            ? this.rebuildError
            : rebuildError as String?,
      );

  static const _sentinel = Object();
}

/// Backs the Resume sub-screen: shows stored resume metadata, replaces the file,
/// and (opt-in) rebuilds the search profile from it via the async job queue.
class ResumeController extends Notifier<ResumeState> {
  static const _pollEvery = Duration(milliseconds: 500);
  static const _pollTimeout = Duration(seconds: 40);

  @override
  ResumeState build() {
    _load();
    return const ResumeState();
  }

  Future<void> _load() async {
    try {
      final info = await ref.read(accountRepositoryProvider).getResume();
      state = state.copyWith(loading: false, resume: info);
    } catch (e) {
      state = state.copyWith(loading: false, error: '$e');
    }
  }

  Future<void> replace({
    required List<int> bytes,
    required String filename,
    String? contentType,
  }) async {
    state = state.copyWith(uploading: true, error: null);
    try {
      final info = await ref.read(accountRepositoryProvider).uploadResume(
            bytes: bytes,
            filename: filename,
            contentType: contentType,
          );
      // A replaced resume invalidates any prior rebuild result.
      state = state.copyWith(
          uploading: false, resume: info, rebuild: RebuildPhase.idle);
    } catch (e) {
      state = state.copyWith(uploading: false, error: _humanize(e));
    }
  }

  /// Enqueue a resume-driven profile rebuild and poll it to completion. On
  /// success the server-side profile is overwritten; the Search-profile editor
  /// re-reads it on its next open.
  Future<void> rebuildProfile() async {
    state = state.copyWith(rebuild: RebuildPhase.running, rebuildError: null);
    try {
      final jobId = await ref.read(accountRepositoryProvider).buildProfileFromResume();
      final job = await _pollJob(jobId);
      if (job.isFailed) {
        state = state.copyWith(
            rebuild: RebuildPhase.failed,
            rebuildError: job.error ?? 'The rebuild failed. Try again.');
      } else {
        state = state.copyWith(rebuild: RebuildPhase.done);
      }
    } catch (e) {
      state = state.copyWith(
          rebuild: RebuildPhase.failed, rebuildError: _humanize(e));
    }
  }

  Future<JobRecord> _pollJob(String jobId) async {
    final deadline = DateTime.now().add(_pollTimeout);
    while (DateTime.now().isBefore(deadline)) {
      final job = await ref.read(accountRepositoryProvider).getJob(jobId);
      if (job.isDone) return job;
      await Future.delayed(_pollEvery);
    }
    throw TimeoutException('The rebuild took too long. Try again in a moment.');
  }

  String _humanize(Object e) {
    if (e is TimeoutException) return e.message ?? 'Timed out. Try again.';
    return 'Something went wrong. Check your connection and try again.';
  }
}

final resumeControllerProvider =
    NotifierProvider.autoDispose<ResumeController, ResumeState>(
        ResumeController.new);
