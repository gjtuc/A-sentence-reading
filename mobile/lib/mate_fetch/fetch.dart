/// design/251 — device GET of mate PDF bytes (never via Cloud Run proxy).
library;

import 'dart:typed_data';

import 'package:http/http.dart' as http;

import 'validate.dart';

class MateFetchOutcome {
  const MateFetchOutcome({
    required this.ok,
    this.bytes,
    this.code = '',
    this.host = '',
    this.finalUrl = '',
    this.redirects = 0,
  });

  final bool ok;
  final Uint8List? bytes;
  final String code;
  final String host;
  final String finalUrl;
  final int redirects;
}

Future<MateFetchOutcome> fetchMatePdfBytes(
  String url, {
  http.Client? client,
  int maxBytes = kMateFetchMaxBytes,
  int maxRedirects = kMateFetchMaxRedirects,
  Duration timeout = const Duration(seconds: 45),
}) async {
  final owned = client == null;
  final httpClient = client ?? http.Client();
  try {
    var current = Uri.tryParse(url.trim());
    if (current == null || !(current.isScheme('https') || current.isScheme('http'))) {
      return const MateFetchOutcome(ok: false, code: 'bad_url');
    }
    if (!mateHostAllowed(current.host)) {
      return MateFetchOutcome(
        ok: false,
        code: 'bad_host',
        host: current.host,
        finalUrl: current.toString(),
      );
    }
    var redirects = 0;
    while (true) {
      final req = http.Request('GET', current!)
        ..followRedirects = false
        ..headers['User-Agent'] = 'A-sentence-reading/mate-fetch'
        ..headers['Accept'] = 'application/pdf,application/zip,*/*';
      final streamed = await httpClient.send(req).timeout(timeout);
      if (streamed.statusCode >= 300 &&
          streamed.statusCode < 400 &&
          streamed.headers['location'] != null) {
        redirects += 1;
        if (redirects > maxRedirects) {
          await streamed.stream.drain();
          return MateFetchOutcome(
            ok: false,
            code: 'too_many_redirects',
            host: current.host,
            finalUrl: current.toString(),
            redirects: redirects,
          );
        }
        final next = Uri.tryParse(streamed.headers['location']!.trim());
        await streamed.stream.drain();
        if (next == null) {
          return MateFetchOutcome(
            ok: false,
            code: 'bad_redirect',
            host: current.host,
            redirects: redirects,
          );
        }
        current = next.hasScheme ? next : current.resolveUri(next);
        if (!mateHostAllowed(current.host)) {
          return MateFetchOutcome(
            ok: false,
            code: 'bad_host',
            host: current.host,
            finalUrl: current.toString(),
            redirects: redirects,
          );
        }
        continue;
      }
      if (streamed.statusCode < 200 || streamed.statusCode >= 300) {
        await streamed.stream.drain();
        return MateFetchOutcome(
          ok: false,
          code: 'http_${streamed.statusCode}',
          host: current.host,
          finalUrl: current.toString(),
          redirects: redirects,
        );
      }
      final builder = BytesBuilder(copy: false);
      await for (final chunk in streamed.stream) {
        if (builder.length + chunk.length > maxBytes) {
          return MateFetchOutcome(
            ok: false,
            code: 'too_large',
            host: current.host,
            finalUrl: current.toString(),
            redirects: redirects,
          );
        }
        builder.add(chunk);
      }
      final bytes = builder.takeBytes();
      final v = validateMateBytes(bytes, maxBytes: maxBytes);
      if (!v.ok) {
        return MateFetchOutcome(
          ok: false,
          code: v.code.name,
          host: current.host,
          finalUrl: current.toString(),
          redirects: redirects,
        );
      }
      return MateFetchOutcome(
        ok: true,
        bytes: Uint8List.fromList(bytes),
        code: 'ok',
        host: current.host,
        finalUrl: current.toString(),
        redirects: redirects,
      );
    }
  } catch (_) {
    return const MateFetchOutcome(ok: false, code: 'network');
  } finally {
    if (owned) httpClient.close();
  }
}
