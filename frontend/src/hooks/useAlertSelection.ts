import { useState, useCallback, useMemo, useEffect } from 'react';

export function useAlertSelection(alertIds: string[]) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Clear selection of alerts that no longer exist
  useEffect(() => {
    setSelectedIds((prev) => {
      const validIds = new Set(alertIds);
      const filtered = new Set(Array.from(prev).filter(id => validIds.has(id)));
      // Only update if something changed
      if (filtered.size !== prev.size) {
        return filtered;
      }
      return prev;
    });
  }, [alertIds]);

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

  /**
   * Substitui a seleção pelos ids informados.
   *
   * Existe para a ação em lote parcial: quando 18 de 20 alertas são
   * reconhecidos e 2 falham, limpar tudo esconderia quais precisam de nova
   * tentativa. Deixar só os que falharam selecionados transforma o próximo
   * clique na repetição exata do que faltou.
   */
  const selecionarApenas = useCallback((ids: string[]) => {
    setSelectedIds(new Set(ids));
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
    selecionarApenas,
    isSelected,
  };
}
