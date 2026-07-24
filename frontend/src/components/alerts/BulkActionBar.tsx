import React, { useCallback } from 'react';
import { Check, X, MoreHorizontal, AlertCircle } from 'lucide-react';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '../ui/dropdown-menu';

interface BulkActionBarProps {
  selectedCount: number;
  isLoading?: boolean;
  onAcknowledgeAll: () => Promise<void>;
  onCompleteAll: () => Promise<void>;
  onClearSelection: () => void;
}

export function BulkActionBar({
  selectedCount,
  isLoading = false,
  onAcknowledgeAll,
  onCompleteAll,
  onClearSelection,
}: BulkActionBarProps) {
  const [isProcessing, setIsProcessing] = React.useState(false);

  const handleAcknowledgeAll = useCallback(async () => {
    setIsProcessing(true);
    try {
      await onAcknowledgeAll();
    } finally {
      setIsProcessing(false);
    }
  }, [onAcknowledgeAll]);

  const handleCompleteAll = useCallback(async () => {
    setIsProcessing(true);
    try {
      await onCompleteAll();
    } finally {
      setIsProcessing(false);
    }
  }, [onCompleteAll]);

  if (selectedCount === 0) {
    return null;
  }

  return (
    <div className="sticky bottom-0 left-0 right-0 bg-white border-t border-gray-200 shadow-lg p-4 flex items-center justify-between gap-4 rounded-lg animate-in slide-in-from-bottom-2">
      {/* Left Side: Selection Info */}
      <div className="flex items-center gap-3">
        <Badge variant="default" className="text-base px-3 py-1">
          {selectedCount} selecionado{selectedCount !== 1 ? 's' : ''}
        </Badge>
        <p className="text-sm text-gray-600">
          Escolha uma ação abaixo para prosseguir
        </p>
      </div>

      {/* Right Side: Actions */}
      <div className="flex items-center gap-2">
        {/* Acknowledge Button */}
        <Button
          variant="outline"
          size="sm"
          onClick={handleAcknowledgeAll}
          disabled={isProcessing || isLoading}
          className="flex items-center gap-2"
          title="Reconhecer todos os alertas selecionados"
        >
          <AlertCircle className="w-4 h-4" />
          Reconhecer ({selectedCount})
        </Button>

        {/* Complete Button */}
        <Button
          variant="default"
          size="sm"
          onClick={handleCompleteAll}
          disabled={isProcessing || isLoading}
          className="flex items-center gap-2"
          title="Completar todos os alertas selecionados"
        >
          <Check className="w-4 h-4" />
          Completar ({selectedCount})
        </Button>

        {/* More Options */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              disabled={isProcessing || isLoading}
            >
              <MoreHorizontal className="w-4 h-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={handleAcknowledgeAll} disabled={isProcessing}>
              <AlertCircle className="w-4 h-4 mr-2" />
              Reconhecer Todos
            </DropdownMenuItem>
            <DropdownMenuItem onClick={handleCompleteAll} disabled={isProcessing}>
              <Check className="w-4 h-4 mr-2" />
              Completar Todos
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={onClearSelection} disabled={isProcessing}>
              <X className="w-4 h-4 mr-2" />
              Limpar Seleção
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>

        {/* Clear Selection Button */}
        <Button
          variant="ghost"
          size="sm"
          onClick={onClearSelection}
          disabled={isProcessing || isLoading}
          className="flex items-center gap-1"
          title="Limpar seleção"
        >
          <X className="w-4 h-4" />
          Limpar
        </Button>
      </div>
    </div>
  );
}
