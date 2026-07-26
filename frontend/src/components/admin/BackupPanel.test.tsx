/**
 * Painel de backup.
 *
 * O que estes testes protegem é o veredito: `saudavel` é a única resposta à
 * pergunta "estou coberto?", e antes desta tela a única evidência de que o
 * backup funcionava era uma linha de log que ninguém lê.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { BackupPanel } from './BackupPanel';
import type { BackupItem, BackupStatus, EstadoReplicacao } from '../../lib/api';

vi.mock('../../lib/api', async (importarOriginal) => {
  const original = await importarOriginal<typeof import('../../lib/api')>();
  return {
    ...original,
    backupApi: {
      criar: vi.fn(),
      listar: vi.fn(),
      status: vi.fn(),
      verificar: vi.fn(),
      limpar: vi.fn(),
    },
  };
});

import { backupApi } from '../../lib/api';

const arquivo = (over: Partial<BackupItem> = {}): BackupItem => ({
  filename: 'backup_20260701_030000.db',
  size_mb: 17.4,
  created_at: '2026-07-01T03:00:00',
  age_hours: 5,
  ...over,
});

const semReplicacao = (over: Partial<EstadoReplicacao> = {}): EstadoReplicacao => ({
  configurada: false,
  intervalo_horas: null,
  ok: null,
  idade_horas: null,
  destino: null,
  arquivos: null,
  erro: null,
  saudavel: false,
  ...over,
});

const estado = (over: Partial<BackupStatus> = {}): BackupStatus => ({
  total: 1,
  validos: 1,
  invalidos: [],
  ultimo_valido: 'backup_20260701_030000.db',
  idade_horas: 5,
  proporcional: true,
  saudavel: true,
  replicacao: semReplicacao(),
  ...over,
});

beforeEach(() => {
  vi.mocked(backupApi.status).mockResolvedValue(estado());
  vi.mocked(backupApi.listar).mockResolvedValue({ backups: [arquivo()], count: 1 });
  vi.mocked(backupApi.criar).mockResolvedValue({ ok: true, filename: 'backup_novo.db' });
  vi.mocked(backupApi.verificar).mockResolvedValue({ backups: [arquivo({ ok: true })], invalidos: 0 });
  vi.mocked(backupApi.limpar).mockResolvedValue({ ok: true, removed_count: 2 });
});

describe('veredito de cobertura', () => {
  it('afirma cobertura quando o backup esta saudavel', async () => {
    render(<BackupPanel />);
    expect(await screen.findByText(/backup em dia e utilizável/i)).toBeInTheDocument();
  });

  it('avisa quando nao ha backup confiavel', async () => {
    vi.mocked(backupApi.status).mockResolvedValue(
      estado({ saudavel: false, validos: 0, ultimo_valido: null, idade_horas: null })
    );
    render(<BackupPanel />);
    expect(await screen.findByText(/sem backup confiável/i)).toBeInTheDocument();
  });

  it('denuncia backup desproporcional ao banco vivo', async () => {
    // Um backup pode ser íntegro, recentíssimo e ainda ser cópia de OUTRO
    // banco — já aconteceu, com a suíte de testes gravando no diretório real.
    // Íntegro e recente não pode ser lido como "coberto".
    vi.mocked(backupApi.status).mockResolvedValue(estado({ proporcional: false, saudavel: false }));
    render(<BackupPanel />);
    expect(await screen.findByText(/pequeno demais/i)).toBeInTheDocument();
  });

  it('lista os arquivos que nao restauram', async () => {
    vi.mocked(backupApi.status).mockResolvedValue(
      estado({ saudavel: false, invalidos: ['backup_corrompido.db'] })
    );
    render(<BackupPanel />);
    expect(await screen.findByText(/backup_corrompido\.db/)).toBeInTheDocument();
  });
});

describe('estado de verificacao dos arquivos', () => {
  it('nao afirma integridade antes de verificar', async () => {
    // Ausência de selo é "não verificado", e não "íntegro": dizer o contrário
    // criaria confiança que nada sustenta.
    render(<BackupPanel />);
    expect(await screen.findByText('Não verificado')).toBeInTheDocument();
  });

  it('marca os arquivos apos verificar', async () => {
    render(<BackupPanel />);
    await screen.findByText('Não verificado');

    await userEvent.click(screen.getByRole('button', { name: /verificar todos/i }));

    expect(await screen.findByText('Restaura')).toBeInTheDocument();
  });
});

describe('acoes', () => {
  it('cria backup sob demanda', async () => {
    render(<BackupPanel />);
    await screen.findByText(/backup em dia/i);

    await userEvent.click(screen.getByRole('button', { name: /criar backup agora/i }));

    await waitFor(() => expect(backupApi.criar).toHaveBeenCalled());
  });

  it('limpeza exige confirmacao', async () => {
    render(<BackupPanel />);
    await screen.findByText(/backup em dia/i);

    await userEvent.click(screen.getByRole('button', { name: /remover mais antigos/i }));

    // Apagar backup é irreversível e pode deixar a instalação descoberta.
    expect(backupApi.limpar).not.toHaveBeenCalled();
    expect(await screen.findByRole('alertdialog')).toBeInTheDocument();
  });

  it('bloqueia limpeza com zero dias', async () => {
    // `keep_days=0` apagaria TODOS os backups — o endpoint aceita, a tela não.
    render(<BackupPanel />);
    await screen.findByText(/backup em dia/i);

    const campo = screen.getByLabelText(/manter os últimos/i);
    await userEvent.clear(campo);
    await userEvent.type(campo, '0');

    expect(screen.getByRole('button', { name: /remover mais antigos/i })).toBeDisabled();
  });
});
