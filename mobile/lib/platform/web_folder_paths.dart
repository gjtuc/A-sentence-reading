/// design/416 - names for a folder connected on the web; no browser calls here.
library;

const String kWebFolderScheme = 'webdir:';

String webFolderTreeUri(String key) => '$kWebFolderScheme$key';

String webFolderDocUri(String key, String path) => '$kWebFolderScheme$key/$path';

/// The IndexedDB key of a connected folder, or null for any other uri.
String? webFolderKey(String treeUri) {
  final u = treeUri.trim();
  if (!u.startsWith(kWebFolderScheme)) return null;
  final key = u.substring(kWebFolderScheme.length);
  if (key.isEmpty || key.contains('/')) return null;
  return key;
}

/// Folder key and the path inside it, or null when [docUri] is not a file in one.
({String key, String path})? webFolderDocParts(String docUri) {
  final u = docUri.trim();
  if (!u.startsWith(kWebFolderScheme)) return null;
  final rest = u.substring(kWebFolderScheme.length);
  final slash = rest.indexOf('/');
  if (slash <= 0 || slash == rest.length - 1) return null;
  final path = rest.substring(slash + 1);
  if (path.split('/').any((s) => s.isEmpty || s == '.' || s == '..')) return null;
  return (key: rest.substring(0, slash), path: path);
}

/// The phone lists the same two kinds (SafTreeHandler).
bool webFolderListable(String name) {
  final lower = name.toLowerCase();
  return lower.endsWith('.pdf') || lower.endsWith('.docx');
}
