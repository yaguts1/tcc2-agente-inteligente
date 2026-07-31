/**
 * Quais leitos são meus, e o botão de assumir/liberar.
 *
 * O filtro do servidor (`apenas_meus`) é o que de fato reduz a lista. Este hook
 * existe para a outra metade: a tela precisa saber quais linhas são suas
 * **mesmo com o filtro desligado**, senão a única forma de descobrir seria
 * ligar o filtro — e aí não dá para ver o resto da ala e os seus leitos ao
 * mesmo tempo, que é justamente o que a coordenação e quem cobre um colega
 * precisam.
 */
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { triagemApi } from '../lib/api';

export function useMeusPacientes() {
  const [meus, setMeus] = useState<Set<string>>(new Set());
  const [carregando, setCarregando] = useState(true);

  const recarregar = useCallback(async () => {
    try {
      setMeus(new Set(await triagemApi.meusPacientes()));
    } catch {
      // Falhar aqui não pode esconder a lista: sem a informação de posse, a
      // tela volta a ser a de antes — completa, e sem marcação. Degrada, não
      // quebra.
      setMeus(new Set());
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    void recarregar();
  }, [recarregar]);

  const alternar = useCallback(
    async (pacienteId: string) => {
      const era = meus.has(pacienteId);
      // Otimista: assumir um leito é uma ação de organização pessoal, e esperar
      // o servidor para ver o efeito faz a pessoa tocar de novo. O servidor é
      // idempotente nas duas direções, então o pior caso de um toque duplo é
      // uma requisição a mais.
      setMeus((antes) => {
        const novo = new Set(antes);
        if (era) novo.delete(pacienteId);
        else novo.add(pacienteId);
        return novo;
      });

      try {
        if (era) await triagemApi.liberar(pacienteId);
        else await triagemApi.assumir(pacienteId);
      } catch {
        toast.error(era ? 'Não foi possível liberar' : 'Não foi possível assumir');
        await recarregar();
      }
    },
    [meus, recarregar],
  );

  const liberarTodos = useCallback(async () => {
    try {
      await triagemApi.liberarTodos();
      setMeus(new Set());
      toast.success('Leitos liberados');
    } catch {
      toast.error('Não foi possível liberar os leitos');
      await recarregar();
    }
  }, [recarregar]);

  return { meus, carregando, alternar, liberarTodos, recarregar };
}
