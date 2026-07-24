import { Spinner } from './Spinner';

interface LoadingOverlayProps {
  message?: string;
}

export function LoadingOverlay({ message = 'Carregando...' }: LoadingOverlayProps) {
  return (
    <div className="absolute inset-0 bg-background/80 backdrop-blur-sm flex items-center justify-center z-50 rounded-lg">
      <div className="text-center">
        <Spinner size="lg" />
        <p className="mt-4 text-muted-foreground">{message}</p>
      </div>
    </div>
  );
}
