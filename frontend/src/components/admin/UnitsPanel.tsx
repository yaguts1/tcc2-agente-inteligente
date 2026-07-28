/**
 * Unidades (alas/setores) e quem enxerga cada uma.
 *
 * O escopo por unidade é regra de SEGURANÇA, não de apresentação: é o que
 * impede toda enfermeira do prédio de ler o dado clínico de todo paciente — e a
 * trilha de auditoria registra esse acesso fielmente, o que a transformaria de
 * defesa em prova.
 *
 * Duas regras do backend que esta tela precisa refletir, não reimplementar:
 *
 *  - lista VAZIA é válida e significa "não vê nada" (deny by default). Não é o
 *    mesmo que admin: admin vê tudo por causa do PAPEL, e esta lista não o
 *    restringe. A tela precisa deixar essa diferença explícita, porque "sem
 *    unidades" e "todas as unidades" são visualmente parecidos e clinicamente
 *    opostos;
 *  - alterar o vínculo tem efeito imediato — o backend limpa o cache da
 *    listagem de alertas, senão o usuário seguiria vendo por até 30s a ala da
 *    qual acabou de ser removido.
 */
import { useEffect, useState } from 'react';
import { unitsApi, usuariosApi, Unit, Usuario, ApiException } from '../../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Checkbox } from '../ui/checkbox';
import { Skeleton } from '../ui/skeleton';
import { ErrorBanner } from '../shared/ErrorBanner';
import { Spinner } from '../shared/Spinner';
import { Building2, Plus, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

export function UnitsPanel() {
  const [unidades, setUnidades] = useState<Unit[]>([]);
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [vinculos, setVinculos] = useState<Record<string, number[]>>({});
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState<string | null>(null);
  const [novoNome, setNovoNome] = useState('');
  const [criando, setCriando] = useState(false);

  const carregar = async () => {
    setCarregando(true);
    try {
      const [listaUnidades, listaUsuarios] = await Promise.all([
        unitsApi.list(),
        usuariosApi.listar(),
      ]);
      setUnidades(listaUnidades);
      setUsuarios(listaUsuarios);

      // Um pedido por usuário: a API não expõe o mapa inteiro, e inventar um
      // endpoint agregado só para a tela adicionaria superfície sem necessidade
      // — o número de contas de uma ala é pequeno.
      const mapa: Record<string, number[]> = {};
      await Promise.all(
        listaUsuarios.map(async (u) => {
          try {
            mapa[u.username] = (await unitsApi.getUserUnits(u.username)).unidades;
          } catch {
            mapa[u.username] = [];
          }
        }),
      );
      setVinculos(mapa);
      setErro(null);
    } catch (e) {
      setErro(e instanceof ApiException ? e.message : 'Falha ao carregar unidades');
    } finally {
      setCarregando(false);
    }
  };

  useEffect(() => {
    void carregar();
  }, []);

  const criarUnidade = async () => {
    const nome = novoNome.trim();
    if (!nome) return;
    setCriando(true);
    try {
      await unitsApi.create(nome);
      setNovoNome('');
      toast.success(`Unidade "${nome}" criada`);
      await carregar();
    } catch (e) {
      toast.error(e instanceof ApiException ? e.message : 'Falha ao criar unidade');
    } finally {
      setCriando(false);
    }
  };

  const alternarVinculo = async (username: string, unidadeId: number, marcado: boolean) => {
    const atual = vinculos[username] ?? [];
    const proximo = marcado
      ? [...atual, unidadeId]
      : atual.filter((id) => id !== unidadeId);

    setSalvando(username);
    try {
      await unitsApi.setUserUnits(username, proximo);
      setVinculos({ ...vinculos, [username]: proximo });
      if (proximo.length === 0) {
        // Aviso explícito: a tela dessa pessoa fica vazia a partir de agora, e
        // isso é silencioso do lado dela.
        toast.warning(`${username} não enxerga mais nenhuma unidade`);
      } else {
        toast.success(`Unidades de ${username} atualizadas`);
      }
    } catch (e) {
      toast.error(e instanceof ApiException ? e.message : 'Falha ao salvar vínculo');
    } finally {
      setSalvando(null);
    }
  };

  if (carregando) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {erro && <ErrorBanner message={erro} onRetry={carregar} />}

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <Building2 className="w-5 h-5" aria-hidden="true" />
            Unidades
          </CardTitle>
          <Button variant="outline" size="sm" onClick={carregar} aria-label="Recarregar">
            <RefreshCw className="w-4 h-4" aria-hidden="true" />
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {unidades.map((u) => (
              <Badge key={u.id} variant="secondary">
                {u.nome}
              </Badge>
            ))}
          </div>

          <div className="flex flex-col sm:flex-row gap-2 sm:items-end">
            <div className="flex-1 space-y-2">
              <Label htmlFor="nova-unidade">Nova unidade</Label>
              <Input
                id="nova-unidade"
                value={novoNome}
                placeholder="ex: Ala Sul"
                onChange={(e) => setNovoNome(e.target.value)}
                disabled={criando}
              />
            </div>
            <Button onClick={criarUnidade} disabled={criando || !novoNome.trim()}>
              {criando ? <Spinner /> : <Plus className="w-4 h-4 mr-1" aria-hidden="true" />}
              Criar
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Quem enxerga o quê</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {usuarios.map((usuario) => {
            const ehAdmin = usuario.role === 'admin';
            const doUsuario = vinculos[usuario.username] ?? [];
            return (
              <div key={usuario.username} className="border-b pb-3 last:border-b-0">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-medium">{usuario.username}</span>
                  {salvando === usuario.username && <Spinner />}
                </div>

                {ehAdmin ? (
                  // Admin não é "todas as unidades marcadas": ele ignora a
                  // lista. Mostrar caixas marcadas sugeriria que desmarcar
                  // restringe — e não restringe.
                  <p className="text-sm text-muted-foreground">
                    Administrador: enxerga todas as unidades, por papel.
                  </p>
                ) : (
                  <>
                    <div className="flex flex-wrap gap-4">
                      {unidades.map((u) => (
                        <label
                          key={u.id}
                          className="flex items-center gap-2 text-sm cursor-pointer"
                        >
                          <Checkbox
                            checked={doUsuario.includes(u.id)}
                            onCheckedChange={(marcado) =>
                              alternarVinculo(usuario.username, u.id, marcado === true)
                            }
                            disabled={salvando === usuario.username}
                          />
                          {u.nome}
                        </label>
                      ))}
                    </div>
                    {doUsuario.length === 0 && (
                      <p className="text-xs text-warning mt-2" role="alert">
                        Sem unidade: esta conta não vê paciente nem alerta nenhum.
                      </p>
                    )}
                  </>
                )}
              </div>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}
