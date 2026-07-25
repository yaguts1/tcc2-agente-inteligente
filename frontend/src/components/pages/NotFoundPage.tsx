import { Link, useLocation } from 'react-router-dom';
import { FileQuestion } from 'lucide-react';
import { Button } from '../ui/button';

/**
 * Página para URLs desconhecidas.
 *
 * Antes não existia: a navegação era um `switch` sobre estado e o `default`
 * caía no Dashboard. Um link quebrado ou um endereço digitado errado levava
 * silenciosamente à tela inicial, como se tudo estivesse certo — o usuário
 * ficava sem saber que a página que procurava não existe.
 */
export function NotFoundPage() {
  const { pathname } = useLocation();

  return (
    <div className="flex flex-col items-center justify-center py-16 text-center" role="alert">
      <FileQuestion className="mb-4 h-12 w-12 text-muted-foreground" aria-hidden="true" />
      <h1 className="text-foreground">Página não encontrada</h1>
      <p className="mt-2 max-w-md text-muted-foreground">
        O endereço <code className="rounded bg-muted px-1.5 py-0.5">{pathname}</code> não
        corresponde a nenhuma tela do sistema.
      </p>
      <Button asChild className="mt-6">
        <Link to="/">Voltar ao Dashboard</Link>
      </Button>
    </div>
  );
}
