/// Refuse a pre-merge hydrate snapshot when the library row has already moved.
bool shouldReuseHydrateSession({
  required bool sideValid,
  required int sideSentenceCount,
  required int sideFigureCount,
  required bool sideHasImage,
  required bool sideSupplementaryMerged,
  required bool hydrateActive,
  required int entrySentenceCount,
  required int entryFigureCount,
  required String entryRole,
}) {
  if (!sideValid || sideSentenceCount <= 0) return false;
  if (!hydrateActive && !sideHasImage) return false;
  final role = entryRole.trim().toLowerCase();
  if (role == 'merged' && !sideSupplementaryMerged) return false;
  if (entrySentenceCount > 0 && entrySentenceCount != sideSentenceCount) {
    return false;
  }
  if (entryFigureCount > 0 && entryFigureCount != sideFigureCount) {
    return false;
  }
  return true;
}
