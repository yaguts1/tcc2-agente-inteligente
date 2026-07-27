/**
 * Gestão de usuários.
 *
 * As cinco rotas (`/api/usuarios*`) existiam sem nenhuma tela que as
 * consumisse: não havia como listar, promover, desativar ou resetar senha.
 * Numa instalação real isso significa que um profissional que sai da equipe
 * mantém acesso indefinidamente, e que não há como criar um segundo
 * administrador.
 *
 * Três regras do backend que a tela precisa refletir, não reimplementar:
 *  - desativar em vez de apagar (apagar levaria junto a autoria registrada na
 *    timeline: quem reconheceu e quem concluiu cada alerta);
 *  - toda ação sensível revoga as sessões do alvo, senão "desativar" seria
 *    cosmético — o JWT já emitido seguiria valendo por horas;
 *  - a instalação nunca fica sem admin ativo (409 `ultimo_admin`).
 */
import { useEffect, useState } from 'react';
import { usuariosApi, Usuario, PapelUsuario, ApiException, SENHA_MIN_LEN } from '../../lib/api';
import { getStoredUser } from '../../lib/storage';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Skeleton } from '../ui/skeleton';
import { ErrorBanner } from '../shared/ErrorBanner';
import { Spinner } from '../shared/Spinner';
import { KeyRound, RefreshCw, ShieldCheck, UserCog, UserPlus, UserX, UserCheck } from 'lucide-react';
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

export function UsersPanel() {
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [processando, setProcessando] = useState<string | null>(null);
  const [resetandoSenhaDe, setResetandoSenhaDe] = useState<Usuario | null>(null);
  const [novaSenha, setNovaSenha] = useState('');
  const [desativando, setDesativando] = useState<Usuario | null>(null);
  const [criando, setCriando] = useState(false);
  const [novoUsuario, setNovoUsuario] = useState({ username: '', senha: '', nome: '' });

  const eu = getStoredUser()?.username;

  const carregar = async () => {
    try {
      setUsuarios(await usuariosApi.listar());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiException ? err.message : 'Erro ao carregar usuários');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    carregar();
  }, []);

  /**
   * Executa a ação e recarrega. O erro do backend é exibido como veio: as
   * mensagens de 409 (`ultimo_admin`, `autodesativacao`) explicam a regra ao
   * usuário melhor do que qualquer texto genérico daqui.
   */
  const executar = async (username: string, acao: () => Promise<unknown>, sucesso: string) => {
    setProcessando(username);
    try {
      await acao();
      toast.success(sucesso);
      await carregar();
      return true;
    } catch (err) {
      toast.error(err instanceof ApiException ? err.message : 'Não foi possível concluir a ação');
      return false;
    } finally {
      setProcessando(null);
    }
  };

  const alternarPapel = (u: Usuario) => {
    const novo: PapelUsuario = u.role === 'admin' ? 'staff' : 'admin';
    return executar(
      u.username,
      () => usuariosApi.alterarPapel(u.username, novo),
      `${u.username} agora é ${novo === 'admin' ? 'administrador' : 'equipe'} — sessões encerradas`
    );
  };

  const confirmarDesativacao = async () => {
    if (!desativando) return;
    const ok = await executar(
      desativando.username,
      () => usuariosApi.alterarAtivo(desativando.username, false),
      `${desativando.username} desativado e sessões encerradas`
    );
    if (ok) setDesativando(null);
  };

  const reativar = (u: Usuario) =>
    executar(u.username, () => usuariosApi.alterarAtivo(u.username, true), `${u.username} reativado`);

  const confirmarResetDeSenha = async () => {
    if (!resetandoSenhaDe) return;
    const ok = await executar(
      resetandoSenhaDe.username,
      () => usuariosApi.definirSenha(resetandoSenhaDe.username, novaSenha),
      `Senha de ${resetandoSenhaDe.username} redefinida — sessões encerradas`
    );
    if (ok) {
      setResetandoSenhaDe(null);
      setNovaSenha('');
    }
  };

  const confirmarCriacao = async () => {
    const ok = await executar(
      novoUsuario.username,
      () =>
        usuariosApi.criar(
          novoUsuario.username.trim(),
          novoUsuario.senha,
          novoUsuario.nome.trim() || undefined
        ),
      `${novoUsuario.username} criado — entra como equipe; promova se precisar`
    );
    if (ok) {
      setCriando(false);
      setNovoUsuario({ username: '', senha: '', nome: '' });
    }
  };

  const podeCriar =
    novoUsuario.username.trim().length > 0 && novoUsuario.senha.length >= SENHA_MIN_LEN;

  const adminsAtivos = usuarios.filter((u) => u.role === 'admin' && u.ativo).length;

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[...Array(4)].map((_, i) => (
          <Skeleton key={i} className="h-20 w-full" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-muted-foreground">
          {usuarios.length} conta{usuarios.length === 1 ? '' : 's'} • {adminsAtivos} admin
          {adminsAtivos === 1 ? '' : 's'} ativo{adminsAtivos === 1 ? '' : 's'}
        </p>
        <div className="flex gap-2">
          <Button variant="outline" onClick={carregar}>
            <RefreshCw className="w-4 h-4 mr-2" />
            Atualizar
          </Button>
          <Button onClick={() => setCriando(true)}>
            <UserPlus className="w-4 h-4 mr-2" />
            Criar usuário
          </Button>
        </div>
      </div>

      {error && (
        <ErrorBanner title="Erro" message={error} onRetry={carregar} onDismiss={() => setError(null)} />
      )}

      <div className="space-y-3">
        {usuarios.map((u) => {
          const ocupado = processando === u.username;
          const souEu = u.username === eu;
          return (
            <Card key={u.username} className={u.ativo ? '' : 'opacity-60'}>
              <CardContent className="flex flex-wrap items-center justify-between gap-4 p-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-foreground">{u.username}</span>
                    {souEu && <Badge variant="outline">você</Badge>}
                    {u.role === 'admin' ? (
                      <Badge className="bg-primary text-primary-foreground">
                        <ShieldCheck className="w-3 h-3 mr-1" />
                        Administrador
                      </Badge>
                    ) : (
                      <Badge variant="secondary">Equipe</Badge>
                    )}
                    {!u.ativo && <Badge variant="destructive">Desativado</Badge>}
                  </div>
                  {u.display_name && (
                    <p className="text-sm text-muted-foreground truncate">{u.display_name}</p>
                  )}
                </div>

                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => alternarPapel(u)}
                    disabled={ocupado}
                  >
                    {ocupado ? <Spinner className="w-4 h-4 mr-2" /> : <UserCog className="w-4 h-4 mr-2" />}
                    {u.role === 'admin' ? 'Tornar equipe' : 'Tornar admin'}
                  </Button>

                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setNovaSenha('');
                      setResetandoSenhaDe(u);
                    }}
                    disabled={ocupado}
                  >
                    <KeyRound className="w-4 h-4 mr-2" />
                    Redefinir senha
                  </Button>

                  {u.ativo ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => setDesativando(u)}
                      disabled={ocupado || souEu}
                      // O backend recusa a autodesativação com 409; desabilitar
                      // aqui evita oferecer uma ação que sempre falharia.
                      title={souEu ? 'Você não pode desativar a própria conta' : undefined}
                    >
                      <UserX className="w-4 h-4 mr-2" />
                      Desativar
                    </Button>
                  ) : (
                    <Button variant="outline" size="sm" onClick={() => reativar(u)} disabled={ocupado}>
                      <UserCheck className="w-4 h-4 mr-2" />
                      Reativar
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card className="border-primary/40">
        <CardHeader>
          <CardTitle className="text-sm">Por que desativar, e não excluir</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground space-y-2">
          <p>
            Excluir a conta levaria junto a <strong>autoria registrada na linha do tempo</strong> —
            quem reconheceu e quem concluiu cada alerta —, que é justamente o que se preserva num
            prontuário. Desativar encerra o acesso sem apagar o histórico.
          </p>
          <p>
            Trocar papel, desativar ou redefinir senha <strong>encerra as sessões abertas</strong> do
            usuário. Sem isso a mudança seria cosmética: o token já emitido continuaria valendo.
          </p>
        </CardContent>
      </Card>

      {/* Criação de conta.
          O cadastro anônimo é fechado assim que existe o primeiro usuário
          (senão bastaria criar uma conta para ver todos os pacientes), e a tela
          de cadastro só aparece deslogado — então criar o segundo usuário da
          instalação não tinha caminho pela interface. */}
      <AlertDialog open={criando} onOpenChange={(aberto: boolean) => !aberto && setCriando(false)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Criar usuário</AlertDialogTitle>
            <AlertDialogDescription>
              A conta nasce como <strong>equipe</strong>. Para torná-la administradora, use
              &quot;Tornar admin&quot; na lista depois de criar.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="novo-username">Usuário</Label>
              <Input
                id="novo-username"
                value={novoUsuario.username}
                onChange={(e) => setNovoUsuario((p) => ({ ...p, username: e.target.value }))}
                autoComplete="off"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="novo-nome">Nome de exibição (opcional)</Label>
              <Input
                id="novo-nome"
                value={novoUsuario.nome}
                onChange={(e) => setNovoUsuario((p) => ({ ...p, nome: e.target.value }))}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="novo-senha">Senha</Label>
              <Input
                id="novo-senha"
                type="password"
                autoComplete="new-password"
                value={novoUsuario.senha}
                onChange={(e) => setNovoUsuario((p) => ({ ...p, senha: e.target.value }))}
                placeholder={`Mínimo de ${SENHA_MIN_LEN} caracteres`}
              />
              {novoUsuario.senha.length > 0 && novoUsuario.senha.length < SENHA_MIN_LEN && (
                <p className="text-sm text-danger">
                  A senha precisa ter ao menos {SENHA_MIN_LEN} caracteres.
                </p>
              )}
            </div>
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                confirmarCriacao();
              }}
              disabled={!podeCriar}
            >
              Criar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Reset de senha */}
      <AlertDialog
        open={resetandoSenhaDe !== null}
        onOpenChange={(aberto: boolean) => !aberto && setResetandoSenhaDe(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Redefinir senha de {resetandoSenhaDe?.username}</AlertDialogTitle>
            <AlertDialogDescription>
              A senha atual será substituída e todas as sessões deste usuário serão encerradas.
              Informe a nova senha ao usuário por um canal seguro.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-2">
            <Label htmlFor="nova-senha">Nova senha</Label>
            <Input
              id="nova-senha"
              type="password"
              value={novaSenha}
              onChange={(e) => setNovaSenha(e.target.value)}
              placeholder={`Mínimo de ${SENHA_MIN_LEN} caracteres`}
              autoComplete="new-password"
            />
            {novaSenha.length > 0 && novaSenha.length < SENHA_MIN_LEN && (
              <p className="text-sm text-danger">A senha precisa ter ao menos {SENHA_MIN_LEN} caracteres.</p>
            )}
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                confirmarResetDeSenha();
              }}
              disabled={novaSenha.length < SENHA_MIN_LEN}
            >
              Redefinir
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Desativação */}
      <AlertDialog
        open={desativando !== null}
        onOpenChange={(aberto: boolean) => !aberto && setDesativando(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Desativar {desativando?.username}?</AlertDialogTitle>
            <AlertDialogDescription>
              O acesso é encerrado imediatamente, inclusive as sessões abertas. O histórico de ações
              da pessoa é preservado, e a conta pode ser reativada depois.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                confirmarDesativacao();
              }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Desativar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
