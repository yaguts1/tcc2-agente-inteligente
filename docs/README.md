# Documentação

Índice do que existe aqui e para que serve. **Ao adicionar um documento,
registre-o nesta tabela.**

| Documento | Assunto |
|---|---|
| [ARQUITETURA_ESP32_LEITO_PACIENTE.md](ARQUITETURA_ESP32_LEITO_PACIENTE.md) | Como um ESP32 é vinculado a um leito e, por ele, a um paciente |
| [FLUXO_INFORMACAO_ESP32_FRONTEND.md](FLUXO_INFORMACAO_ESP32_FRONTEND.md) | Caminho completo do dado: sensor → ingestão → motor de alertas → UI |
| [datetime_and_firmware.md](datetime_and_firmware.md) | Convenção de tempo: o banco guarda timestamps **UTC naive** |
| [ADMIN_PAGE_RECONCILIACAO.md](ADMIN_PAGE_RECONCILIACAO.md) | Reconciliação de eventos órfãos na tela de administração |
| [COMO_USAR_ADMIN.md](COMO_USAR_ADMIN.md) | Uso da página de administração |
| [GUIA_DEMONSTRACAO.md](GUIA_DEMONSTRACAO.md) | Roteiro de demonstração do sistema |
| [esp32_spiffs_upload.md](esp32_spiffs_upload.md) | Gravação de arquivos no SPIFFS do ESP32 |

Na raiz do repositório: [`README.md`](../README.md),
[`ARQUITETURA_DIAGRAMA.md`](../ARQUITETURA_DIAGRAMA.md),
[`JORNADA_INFORMACAO_ESP32.md`](../JORNADA_INFORMACAO_ESP32.md),
[`GUIA_BUILD_DEPLOYMENT.md`](../GUIA_BUILD_DEPLOYMENT.md),
[`CHECKLIST_DEPLOY_PRODUCAO.md`](../CHECKLIST_DEPLOY_PRODUCAO.md).

## Sobre os documentos removidos

Esta pasta tinha 21 arquivos; 14 eram registros de sessões de depuração
(cabeçalho com emoji, `**Data:** DD/MM/AAAA`, `**Status:** ✅`), somando ~5.100
linhas. Vários se contradiziam: `INCONSISTENCIAS_FLUXO_WEBSOCKET.md` afirmava
que o fluxo estava quebrado e `FIX_WEBSOCKET_IMPLEMENTADO.md` que estava
corrigido — ambos versionados. `DIAGNOSTICO_DESALINHAMENTO.md` e
`CORRECOES_ALINHAMENTO_FINAL.md` eram o antes e o depois da mesma sessão, com
dez minutos de diferença.

O caso mais claro do problema: `PROBLEMA_SIMULACAO_SEM_ALERTAS.md` e
`FIX_SIMULACAO.md` descreviam a aba de Histórico vazia após simular e
concluíam *"O código está correto agora"*. Não estava — o bug seguia presente e
só foi corrigido em julho de 2026 (`inserir_alertas` não registrava eventos de
timeline para alertas já fechados, que é o que a simulação em lote sempre
gera). Documento que afirma um estado que não corresponde ao código é pior que
documento nenhum.

O histórico continua no git (`git log --diff-filter=D --name-only`) para quem
precisar consultar.
