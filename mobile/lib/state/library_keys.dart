/// design/457 — which papers sit in the library of the account's other devices.
///
/// Each device sends its whole library (cache id, PDF hash, title key) to
/// `/api/library-keys` and reads the other devices' lists, so the import list can
/// show 「이미 보관」 for a paper kept on the phone while browsing on the web. A
/// paper that leaves a library leaves that device's next list.
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/spot_sync.dart' show spotDeviceId;

final _hex64 = RegExp(r'^[a-f0-9]{64}$');

class LibraryKey {
  const LibraryKey({required this.cacheId, this.hash = '', this.title = ''});

  final String cacheId;
  final String hash;
  final String title;

  Map<String, Object?> toJson() => {
        'c': cacheId,
        if (_hex64.hasMatch(hash)) 'h': hash,
        if (title.isNotEmpty) 't': title,
      };
}

abstract class LibraryKeysTransport {
  /// Device id → `{at, items: [{c, h?, t?}]}`.
  Future<Map<String, Map<String, dynamic>>> all();
  Future<void> put(Map<String, Object?> body);
}

class AccountLibraryKeys extends ChangeNotifier {
  AccountLibraryKeys({
    this.transport,
    Future<String> Function()? deviceId,
    DateTime Function()? clock,
    this.debounce = const Duration(seconds: 3),
  })  : _deviceId = deviceId ?? spotDeviceId,
        _clock = clock ?? DateTime.now;

  LibraryKeysTransport? transport;
  final Future<String> Function() _deviceId;
  final DateTime Function() _clock;
  final Duration debounce;

  String? _uid;
  Set<String> _hashes = const {};
  Set<String> _titles = const {};
  List<LibraryKey>? _pending;
  String _pendingSig = '';
  String _sentSig = '';
  Timer? _timer;
  Future<void>? _pushing;

  static String prefsKey(String? uid) {
    final u = (uid ?? '').trim();
    return 'library_keys_v1_${u.isEmpty ? 'anon' : u}';
  }

  /// PDF hashes / title keys kept on the account's other devices.
  Set<String> get hashes => _hashes;
  Set<String> get titles => _titles;

  Future<void> bindUid(String? uid) async {
    final u = (uid ?? '').trim().isEmpty ? null : uid!.trim();
    if (u == _uid) return;
    _uid = u;
    _timer?.cancel();
    _pending = null;
    _sentSig = '';
    _hashes = const {};
    _titles = const {};
    notifyListeners();
    if (u == null) return;
    await _load(u);
    if (_uid != u) return;
    notifyListeners();
    await pull();
  }

  Future<void> pull() async {
    final t = transport;
    final uid = _uid;
    if (t == null || uid == null) return;
    final Map<String, Map<String, dynamic>> devices;
    final String me;
    try {
      me = await _deviceId();
      devices = await t.all();
    } catch (_) {
      return;
    }
    if (_uid != uid) return;
    final h = <String>{};
    final ti = <String>{};
    for (final e in devices.entries) {
      if (e.key == me) continue;
      final items = e.value['items'];
      if (items is! List) continue;
      for (final it in items) {
        if (it is! Map) continue;
        final hash = it['h'];
        if (hash is String && _hex64.hasMatch(hash)) h.add(hash);
        final title = it['t'];
        if (title is String && title.isNotEmpty) ti.add(title);
      }
    }
    if (setEquals(h, _hashes) && setEquals(ti, _titles)) return;
    _hashes = Set.unmodifiable(h);
    _titles = Set.unmodifiable(ti);
    notifyListeners();
    await _save(uid);
  }

  /// This device's whole library; sent once it has not changed for [debounce].
  void publish(List<LibraryKey> mine) {
    if (_uid == null || transport == null) return;
    final rows = [for (final k in mine) k.toJson()]
      ..sort((a, b) => '${a['c']}'.compareTo('${b['c']}'));
    final sig = jsonEncode(rows);
    if (sig == _sentSig || sig == _pendingSig) return;
    _pending = mine;
    _pendingSig = sig;
    _timer?.cancel();
    _timer = Timer(debounce, () => unawaited(flush()));
  }

  Future<void> flush() async {
    _timer?.cancel();
    final prior = _pushing;
    if (prior != null) await prior;
    final mine = _pending;
    final t = transport;
    final uid = _uid;
    if (mine == null || t == null || uid == null) return;
    final sig = _pendingSig;
    final run = () async {
      try {
        await t.put({
          'dev': await _deviceId(),
          'at': _clock().toUtc().toIso8601String(),
          'items': [for (final k in mine) k.toJson()],
        });
        if (_uid != uid) return;
        _sentSig = sig;
        if (_pendingSig == sig) {
          _pending = null;
          _pendingSig = '';
        }
      } catch (_) {
        if (_pendingSig == sig) _pendingSig = '';
      }
    }();
    _pushing = run;
    await run;
    if (identical(_pushing, run)) _pushing = null;
  }

  Future<void> _load(String uid) async {
    try {
      final p = await SharedPreferences.getInstance();
      final raw = p.getString(prefsKey(uid));
      if (raw == null || raw.isEmpty) return;
      final obj = jsonDecode(raw);
      if (obj is! Map) return;
      _hashes = Set.unmodifiable({
        for (final v in (obj['h'] as List? ?? const [])) if (v is String && _hex64.hasMatch(v)) v,
      });
      _titles = Set.unmodifiable({
        for (final v in (obj['t'] as List? ?? const [])) if (v is String && v.isNotEmpty) v,
      });
    } catch (_) {}
  }

  Future<void> _save(String uid) async {
    try {
      final p = await SharedPreferences.getInstance();
      await p.setString(prefsKey(uid), jsonEncode({'h': _hashes.toList(), 't': _titles.toList()}));
    } catch (_) {}
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }
}
