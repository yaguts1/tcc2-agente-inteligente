import { AlertCircle, WifiOff, XCircle } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '../ui/alert';
import { Button } from '../ui/button';

interface ErrorBannerProps {
  title?: string;
  message: string;
  type?: 'error' | 'offline' | 'warning';
  onRetry?: () => void;
  onDismiss?: () => void;
}

export function ErrorBanner({
  title,
  message,
  type = 'error',
  onRetry,
  onDismiss,
}: ErrorBannerProps) {
  const getIcon = () => {
    switch (type) {
      case 'offline':
        return <WifiOff className="h-4 w-4" />;
      case 'warning':
        return <AlertCircle className="h-4 w-4" />;
      default:
        return <XCircle className="h-4 w-4" />;
    }
  };

  const getVariant = () => {
    switch (type) {
      case 'offline':
      case 'warning':
        return 'default';
      default:
        return 'destructive';
    }
  };

  return (
    <Alert variant={getVariant()} className="mb-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex gap-2">
          {getIcon()}
          <div>
            {title && <AlertTitle>{title}</AlertTitle>}
            <AlertDescription>{message}</AlertDescription>
          </div>
        </div>
        <div className="flex gap-2">
          {onRetry && (
            <Button size="sm" variant="outline" onClick={onRetry}>
              Tentar novamente
            </Button>
          )}
          {onDismiss && (
            <Button
              size="sm"
              variant="ghost"
              onClick={onDismiss}
              className="px-2"
            >
              ×
            </Button>
          )}
        </div>
      </div>
    </Alert>
  );
}
