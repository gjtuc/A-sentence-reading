/// design/308 — move checked library rows as one block, keeping their order.
List<String> moveIdsAsBlock(
  List<String> ids,
  List<String> moving,
  int insertAt,
) {
  if (ids.isEmpty || moving.isEmpty) return List<String>.from(ids);
  final moveSet = moving.toSet();
  final ordered = <String>[
    for (final id in ids)
      if (moveSet.contains(id)) id,
  ];
  if (ordered.isEmpty) return List<String>.from(ids);
  final rest = <String>[
    for (final id in ids)
      if (!moveSet.contains(id)) id,
  ];
  var before = 0;
  final cap = insertAt < 0 ? 0 : insertAt;
  for (var i = 0; i < ids.length && i < cap; i++) {
    if (!moveSet.contains(ids[i])) before += 1;
  }
  if (before > rest.length) before = rest.length;
  return <String>[
    ...rest.sublist(0, before),
    ...ordered,
    ...rest.sublist(before),
  ];
}
