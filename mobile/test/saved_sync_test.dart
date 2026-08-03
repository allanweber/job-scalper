import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:job_scalper/src/data/feed_repository.dart';
import 'package:job_scalper/src/data/models/feed_models.dart';
import 'package:job_scalper/src/data/providers.dart';
import 'package:job_scalper/src/features/feed/feed_controller.dart';
import 'package:job_scalper/src/features/saved/saved_controller.dart';

/// A feed repo whose save/unsave actually flips the stored saved flag, so the
/// Saved tab's reload reflects the change (the shared harness fake only records
/// calls). Also counts getFeed calls to prove a reload happened.
class _MutableFeedRepo implements FeedRepository {
  _MutableFeedRepo(this._items);
  List<FeedItem> _items;
  int feedLoads = 0;

  void _set(String id, bool saved) => _items = [
        for (final i in _items)
          if (i.postingId == id) i.copyWith(saved: saved) else i
      ];

  @override
  Future<Feed> getFeed({int limit = 100, int minScore = 1}) async {
    feedLoads++;
    final items = _items.where((i) => i.score >= minScore).toList();
    return Feed(items: items, count: items.length);
  }

  @override
  Future<void> save(String postingId) async => _set(postingId, true);

  @override
  Future<void> unsave(String postingId) async => _set(postingId, false);

  @override
  Future<void> markSeen(String postingId) async {}

  @override
  Future<String> createDraft(String postingId) async => 'job-1';

  @override
  Future<PostingDetail> getPosting(String postingId) =>
      throw UnimplementedError();
}

FeedItem _item(String id, {bool saved = false, int score = 80}) => FeedItem(
      postingId: id,
      company: 'Co $id',
      title: 'Role $id',
      url: 'https://e/$id',
      remote: true,
      score: score,
      saved: saved,
    );

/// Pump the microtask/event queue so background reloads settle.
Future<void> _settle() => Future<void>.delayed(const Duration(milliseconds: 20));

void main() {
  test('saving from the feed makes the posting appear on the Saved tab',
      () async {
    final repo = _MutableFeedRepo([
      _item('a', saved: true), // already saved
      _item('b'), // not saved yet
    ]);
    final container = ProviderContainer(overrides: [
      feedRepositoryProvider.overrideWithValue(repo),
    ]);
    addTearDown(container.dispose);

    // Instantiate both controllers and let their initial loads finish.
    container.read(feedControllerProvider);
    container.read(savedControllerProvider);
    await _settle();

    var saved = container.read(savedControllerProvider).items;
    expect(saved.map((i) => i.postingId), ['a']);

    // Save "b" from the feed → the Saved tab reloads in the background.
    await container.read(feedControllerProvider.notifier).toggleSave(_item('b'));
    await _settle();

    saved = container.read(savedControllerProvider).items;
    expect(saved.map((i) => i.postingId).toSet(), {'a', 'b'});
  });

  test('unsaving from the feed drops it from the Saved tab', () async {
    final repo = _MutableFeedRepo([
      _item('a', saved: true),
      _item('b', saved: true),
    ]);
    final container = ProviderContainer(overrides: [
      feedRepositoryProvider.overrideWithValue(repo),
    ]);
    addTearDown(container.dispose);

    container.read(feedControllerProvider);
    container.read(savedControllerProvider);
    await _settle();
    expect(container.read(savedControllerProvider).items.length, 2);

    await container
        .read(feedControllerProvider.notifier)
        .toggleSave(_item('a', saved: true));
    await _settle();

    expect(container.read(savedControllerProvider).items.map((i) => i.postingId),
        ['b']);
  });
}
