/**
 * Backup do banco.
 *
 * As cinco rotas (`/api/admin/backup/*`) existiam sem nenhuma tela. O ponto
 * central desta: `saudavel` de `/status` é a única resposta para "estou
 * coberto?" — e antes dela a única evidência de que o backup funcionava era
 * uma linha de log que ninguém lê. O agendador podia estar falhando havia
 * semanas sem que nada na aplicação ficasse diferente de uma instalação sadia,
 * e a descoberta chegaria no dia da restauração.
 */
import { useEffect, useState } from 'react';
import { backupApi, BackupItem, BackupStatus, ApiException } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Skeleton } from '../ui/skeleton';
import { ErrorBanner } from '../shared/ErrorBanner';
import { EmptyState } from '../shared/EmptyState';
import { Spinner } from '../shared/Spinner';
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  HardDriveDownload,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '../ui/alert-dialog';

const DIAS_PADRAO = 7;

export function BackupPanel() {
  const [status, setStatus] = useState<BackupStatus | null>(null);
  const [backups, setBackups] = useState<BackupItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [acao, setAcao] = useState<'criar' | 'verificar' | 'limpar' | null>(null);
  const [confirmandoLimpeza, setConfirmandoLimpeza] = useState(false);
  const [diasParaManter, setDiasParaManter] = useState(String(DIAS_PADRAO));

  const carregar = async () => {
    try {
      const [estado, lista] = await Promise.all([backupApi.status(), backupApi.listar()]);
      setStatus(estado);
      setBackups(lista.backups);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiException ? err.message : 'Erro ao carregar backups');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    carregar();
  }, []);

  const criar = async () => {
    setAcao('criar');
    try {
      const r = await backupApi.criar();
      toast.success(`Backup criado: ${r.filename}`);
      await carregar();
    } catch (err) {
      toast.error(err instanceof ApiException ? err.message : 'Falha ao criar backup');
    } finally {
      setAcao(null);
    }
  };

  const verificar = async () => {
    setAcao('verificar');
    try {
      // Abre cada arquivo e confere se dá para restaurar a partir dele. É a
      // diferença entre "o arquivo existe" e "o arquivo serve".
      const r = await backupApi.verificar();
      setBackups(r.backups);
      if (r.invalidos > 0) {
        toast.error(`${r.invalidos} de ${r.backups.length} backups NÃO restauram`);
      } else {
        toast.success(`${r.backups.length} backups verificados — todos íntegros`);
      }
      setStatus(await backupApi.status());
    } catch (err) {
      toast.error(err instanceof ApiException ? err.message : 'Falha ao verificar backups');
    } finally {
      setAcao(null);
    }
  };

  const limpar = async () => {
    const dias = Number(diasParaManter);
    setAcao('limpar');
    try {
      const r = await backupApi.limpar(dias);
      toast.success(
        r.removed_count === 0
          ? 'Nenhum backup era antigo o suficiente para remover'
          : `${r.removed_count} backup(s) removido(s)`
      );
      setConfirmandoLimpeza(false);
      await carregar();
    } catch (err) {
      toast.error(err instanceof ApiException ? err.message : 'Falha na limpeza');
    } finally {
      setAcao(null);
    }
  };

  const formatarData = (iso: string) =>
    new Date(iso).toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });

  const idade = (horas: number) =>
    horas < 1 ? 'há minutos' : horas < 24 ? `há ${Math.round(horas)}h` : `há ${Math.round(horas / 24)}d`;

  const diasInvalidos = !Number.isInteger(Number(diasParaManter)) || Number(diasParaManter) < 1;

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-28 w-full" />
        {[...Array(3)].map((_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-muted-foreground">Cópias do banco e verificação de que elas restauram</p>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={carregar}>
            <RefreshCw className="w-4 h-4 mr-2" />
            Atualizar
          </Button>
          <Button variant="outline" onClick={verificar} disabled={acao !== null}>
            {acao === 'verificar' ? (
              <Spinner className="w-4 h-4 mr-2" />
            ) : (
              <ShieldCheck className="w-4 h-4 mr-2" />
            )}
            Verificar todos
          </Button>
          <Button onClick={criar} disabled={acao !== null}>
            {acao === 'criar' ? (
              <Spinner className="w-4 h-4 mr-2" />
            ) : (
              <HardDriveDownload className="w-4 h-4 mr-2" />
            )}
            Criar backup agora
          </Button>
        </div>
      </div>

      {error && (
        <ErrorBanner title="Erro" message={error} onRetry={carregar} onDismiss={() => setError(null)} />
      )}

      {/*
        O veredito, no topo e sem rodeios. `saudavel` já combina "recente" com
        "proporcional ao banco vivo" — este último existe porque um backup pode
        ser íntegro, recentíssimo e ainda assim ser cópia de OUTRO banco.
      */}
      {status && (
        <Card
          className={
            status.saudavel ? 'border-success bg-success-light/30' : 'border-danger bg-danger-light/30'
          }
        >
          <CardContent className="flex items-start gap-3 p-4">
            {status.saudavel ? (
              <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success" aria-hidden="true" />
            ) : (
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-danger" aria-hidden="true" />
            )}
            <div className="space-y-1">
              <p className="font-bold text-foreground">
                {status.saudavel
                  ? 'Backup em dia e utilizável'
                  : 'Sem backup confiável — a restauração pode não ser possível'}
              </p>
              <p className="text-sm text-muted-foreground">
                {status.ultimo_valido ? (
                  <>
                    Último válido: <strong>{status.ultimo_valido}</strong>
                    {status.idade_horas != null && <> ({idade(status.idade_horas)})</>} •{' '}
                    {status.validos} de {status.total} íntegros
                  </>
                ) : (
                  <>Nenhum backup íntegro encontrado entre os {status.total} arquivos.</>
                )}
              </p>
              {!status.proporcional && (
                <p className="text-sm text-danger">
                  O backup mais recente é <strong>pequeno demais</strong> em relação ao banco atual —
                  provavelmente é cópia de outro banco. Confira antes de confiar nele.
                </p>
              )}
              {status.invalidos.length > 0 && (
                <p className="text-sm text-danger">
                  Não restauram: {status.invalidos.join(', ')}
                </p>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {backups.length === 0 ? (
        <Card>
          <EmptyState
            icon={Database}
            title="Nenhum backup encontrado"
            description="Crie o primeiro backup ou verifique se o diretório configurado está no volume persistente"
          />
        </Card>
      ) : (
        <div className="space-y-2">
          {backups.map((b) => (
            <Card key={b.filename}>
              <CardContent className="flex flex-wrap items-center justify-between gap-3 p-4">
                <div className="min-w-0">
                  <p className="font-medium text-foreground truncate">{b.filename}</p>
                  <p className="text-sm text-muted-foreground">
                    {formatarData(b.created_at)} • {b.size_mb} MB • {idade(b.age_hours)}
                  </p>
                </div>
                {/* `ok` só existe depois de "Verificar todos": ausência de
                    selo significa "não verificado", não "íntegro". */}
                {b.ok === true && (
                  <Badge className="bg-success text-success-foreground">Restaura</Badge>
                )}
                {b.ok === false && (
                  <Badge variant="destructive" title={b.motivo ?? undefined}>
                    Não restaura
                  </Badge>
                )}
                {b.ok === undefined && <Badge variant="outline">Não verificado</Badge>}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm flex items-center gap-2">
            <Trash2 className="w-4 h-4" />
            Limpeza de backups antigos
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3">
          <div className="space-y-1">
            <Label htmlFor="keep-days">Manter os últimos (dias)</Label>
            <Input
              id="keep-days"
              type="number"
              min={1}
              className="w-32"
              value={diasParaManter}
              onChange={(e) => setDiasParaManter(e.target.value)}
            />
          </div>
          <Button
            variant="outline"
            onClick={() => setConfirmandoLimpeza(true)}
            disabled={acao !== null || diasInvalidos}
          >
            Remover mais antigos
          </Button>
          {diasInvalidos && (
            <p className="text-sm text-danger">
              Informe um número de dias maior que zero — 0 apagaria todos os backups.
            </p>
          )}
        </CardContent>
      </Card>

      <AlertDialog open={confirmandoLimpeza} onOpenChange={setConfirmandoLimpeza}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remover backups com mais de {diasParaManter} dias?</AlertDialogTitle>
            <AlertDialogDescription>
              Os arquivos são apagados do disco e não há como recuperá-los. Se o backup mais recente
              não estiver íntegro, a limpeza pode deixar a instalação sem nenhuma cópia utilizável —
              vale rodar "Verificar todos" antes.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                limpar();
              }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Remover
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
