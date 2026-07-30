/// Auth JSON shapes from `/api/auth/*` (subset used by the Flutter client).
library;

/// Logged-in user as returned by email login / auth status.
class AsrUser {
  AsrUser({
    required this.uid,
    this.email = '',
    this.name = '',
    this.picture = '',
    this.providers = const [],
  });

  /// Tolerant parse — missing keys become empty; never throws on partial maps.
  factory AsrUser.fromJson(Map<String, dynamic>? json) {
    if (json == null) {
      return AsrUser(uid: '');
    }
    final providersRaw = json['providers'];
    List<String> providers = const [];
    if (providersRaw is List) {
      providers = [
        for (final p in providersRaw) '$p'.trim(),
      ].where((s) => s.isNotEmpty).toList();
    } else if (providersRaw is Map) {
      // EDGE: some payloads may use {email: true, …}
      providers = [
        for (final e in providersRaw.entries)
          if (e.value == true) '${e.key}'.trim(),
      ].where((s) => s.isNotEmpty).toList();
    }
    return AsrUser(
      uid: '${json['uid'] ?? ''}'.trim(),
      email: '${json['email'] ?? ''}'.trim(),
      name: '${json['name'] ?? ''}'.trim(),
      picture: '${json['picture'] ?? ''}'.trim(),
      providers: providers,
    );
  }

  final String uid;
  final String email;
  final String name;
  final String picture;
  final List<String> providers;

  bool get isEmpty => uid.isEmpty;

  String get displayLabel {
    if (email.isNotEmpty) return email;
    if (name.isNotEmpty) return name;
    return uid;
  }
}

/// `/api/auth/status` body (plus ok).
class AsrAuthStatus {
  AsrAuthStatus({
    required this.ok,
    required this.authEnabled,
    required this.providers,
    this.user,
    this.clientId,
  });

  factory AsrAuthStatus.fromJson(Map<String, dynamic> json) {
    final prov = json['providers'];
    final map = <String, bool>{
      'google': false,
      'kakao': false,
      'email': false,
    };
    if (prov is Map) {
      for (final k in map.keys) {
        map[k] = prov[k] == true;
      }
    }
    AsrUser? user;
    final u = json['user'];
    if (u is Map<String, dynamic>) {
      final parsed = AsrUser.fromJson(u);
      if (!parsed.isEmpty) user = parsed;
    } else if (u is Map) {
      final parsed = AsrUser.fromJson(Map<String, dynamic>.from(u));
      if (!parsed.isEmpty) user = parsed;
    }
    final cid = '${json['client_id'] ?? ''}'.trim();
    return AsrAuthStatus(
      ok: json['ok'] == true,
      authEnabled: json['auth_enabled'] == true,
      providers: Map<String, bool>.unmodifiable(map),
      user: user,
      clientId: cid.isEmpty ? null : cid,
    );
  }

  final bool ok;
  final bool authEnabled;
  final Map<String, bool> providers;
  final AsrUser? user;
  /// Google Web client id from server (public; not a secret).
  final String? clientId;

  bool get emailEnabled => providers['email'] == true;
  bool get googleEnabled => providers['google'] == true;
  bool get kakaoEnabled => providers['kakao'] == true;
}
