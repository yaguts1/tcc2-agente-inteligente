import { Loader2 } from 'lucide-react';
import { cn } from '../ui/utils';

interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const sizeMap = {
  sm: 'w-4 h-4',
  md: 'w-6 h-6',
  lg: 'w-8 h-8',
};

export function Spinner({ size = 'md', className }: SpinnerProps) {
  return (
    <Loader2
      className={cn('animate-spin text-primary', sizeMap[size], className)}
    />
  );
}

export function FullPageSpinner() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-bg">
      <div className="text-center">
        <Spinner size="lg" />
        <p className="mt-4 text-text-muted">Carregando...</p>
      </div>
    </div>
  );
}
