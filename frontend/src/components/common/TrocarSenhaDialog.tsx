/**
 * Troca da própria senha.
 *
 * `POST /api/usuarios/eu/senha` existia sem nenhuma tela — trocar a própria
 * senha só era possível por `curl`, ou pedindo a um administrador que
 * redefinisse a sua (o que expõe a senha a um terceiro).
 *
 * Duas regras do backend que a tela precisa honrar:
 *  - exige a senha ATUAL, para que uma sessão aberta esquecida não permita a
 *    tomada da conta;
 *  - a troca ENCERRA todas as sessões, inclusive esta. É o comportamento
 *    esperado de quem troca a senha justamente por suspeitar de acesso
 *    indevido — e por isso a tela avisa antes e desconecta depois, em vez de
 *    deixar o usuário clicando e recebendo 401 sem entender.
 */
import { useState } from 'react';
import { usuariosApi, ApiException } from '../../lib/api';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Spinner } from '../shared/Spinner';
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

const SENHA_MIN = 8;

interface TrocarSenhaDialogProps {
  aberto: boolean;
  onOpenChange: (aberto: boolean) => void;
  /** Chamado após a troca: a sessão foi encerrada no servidor. */
  onSessaoEncerrada: () => void;
}

export function TrocarSenhaDialog({
  aberto,
  onOpenChange,
  onSessaoEncerrada,
}: TrocarSenhaDialogProps) {
  const [senhaAtual, setSenhaAtual] = useState('');
  const [novaSenha, setNovaSenha] = useState('');
  const [confirmacao, setConfirmacao] = useState('');
  const [enviando, setEnviando] = useState(false);

  const curta = novaSenha.length > 0 && novaSenha.length < SENHA_MIN;
  const naoConfere = confirmacao.length > 0 && confirmacao !== novaSenha;
  const podeEnviar =
    senhaAtual.length > 0 && novaSenha.length >= SENHA_MIN && confirmacao === novaSenha;

  const limpar = () => {
    setSenhaAtual('');
    setNovaSenha('');
    setConfirmacao('');
  };

  const enviar = async () => {
    setEnviando(true);
    try {
      await usuariosApi.trocarPropriaSenha(senhaAtual, novaSenha);
      limpar();
      onOpenChange(false);
      toast.success('Senha alterada. Entre novamente com a nova senha.');
      // A sessão já não vale no servidor; sair daqui evita a sequência de 401
      // que o usuário não teria como interpretar.
      onSessaoEncerrada();
    } catch (err) {
      toast.error(
        err instanceof ApiException ? err.message : 'Não foi possível alterar a senha'
      );
    } finally {
      setEnviando(false);
    }
  };

  return (
    <AlertDialog
      open={aberto}
      onOpenChange={(estado: boolean) => {
        if (!estado) limpar();
        onOpenChange(estado);
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Trocar minha senha</AlertDialogTitle>
          <AlertDialogDescription>
            Ao confirmar, <strong>todas as suas sessões serão encerradas</strong> — inclusive esta —
            e você precisará entrar de novo.
          </AlertDialogDescription>
        </AlertDialogHeader>

        <div className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="senha-atual">Senha atual</Label>
            <Input
              id="senha-atual"
              type="password"
              autoComplete="current-password"
              value={senhaAtual}
              onChange={(e) => setSenhaAtual(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="senha-nova">Nova senha</Label>
            <Input
              id="senha-nova"
              type="password"
              autoComplete="new-password"
              value={novaSenha}
              onChange={(e) => setNovaSenha(e.target.value)}
              placeholder={`Mínimo de ${SENHA_MIN} caracteres`}
            />
            {curta && (
              <p className="text-sm text-danger">
                A senha precisa ter ao menos {SENHA_MIN} caracteres.
              </p>
            )}
          </div>
          <div className="space-y-1">
            <Label htmlFor="senha-confirmacao">Repita a nova senha</Label>
            <Input
              id="senha-confirmacao"
              type="password"
              autoComplete="new-password"
              value={confirmacao}
              onChange={(e) => setConfirmacao(e.target.value)}
            />
            {naoConfere && <p className="text-sm text-danger">As senhas não coincidem.</p>}
          </div>
        </div>

        <AlertDialogFooter>
          <AlertDialogCancel disabled={enviando}>Cancelar</AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              e.preventDefault();
              enviar();
            }}
            disabled={!podeEnviar || enviando}
          >
            {enviando && <Spinner className="w-4 h-4 mr-2" />}
            Trocar senha
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
