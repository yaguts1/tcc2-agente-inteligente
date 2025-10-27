import { useState, useCallback, useMemo } from 'react';

export function useAlertSelection(alertIds: string[]) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const toggleAlert = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  }, []);

  const toggleAll = useCallback(() => {
    if (selectedIds.size === alertIds.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(alertIds));
    }
  }, [alertIds, selectedIds.size]);

  const clearSelection = useCallback(() => {
    setSelectedIds(new Set());
  }, []);

  const isSelected = useCallback(
    (id: string) => selectedIds.has(id),
    [selectedIds]
  );

  const selectedCount = selectedIds.size;
  const allSelected = selectedIds.size === alertIds.length && alertIds.length > 0;
  const someSelected = selectedIds.size > 0 && selectedIds.size < alertIds.length;
  const isIndeterminate = someSelected;
  const selectedAlertIds = Array.from(selectedIds);

  return {
    selectedIds: selectedAlertIds,
    selectedCount,
    allSelected,
    someSelected,
    isIndeterminate,
    toggleAlert,
    toggleAll,
    clearSelection,
    isSelected,
  };
}
