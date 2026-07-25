# scripts_demo

Scripts auxiliares de **demonstração e verificação manual**, rodados à mão
contra um servidor já no ar. Não são testes automatizados: a suíte real está em
`tests/` e roda no CI.

A pasta tinha 25 arquivos sem nenhuma explicação, muitos duplicando uns aos
outros ou sobrando de sessões de depuração. Os 15 que nada referenciava foram
removidos; os que ficaram estão listados abaixo. **Se adicionar um script aqui,
registre-o nesta tabela** — senão ele vira o próximo órfão.

| Script | Para que serve | Usado por |
|---|---|---|
| `criar_demo_completa.py` | Popula o banco com um cenário completo de demonstração | manual |
| `gerar_diagrama.py` | Gera os diagramas de arquitetura | `ARQUITETURA_DIAGRAMA.md` |
| `insert_retroactive_events.py` | Insere eventos retroativos para exercitar a reconciliação | `docs/ADMIN_PAGE_RECONCILIACAO.md` |
| `test_export_files.py` | Confere os arquivos gerados pela exportação CSV/PDF | `README.md` |
| `test_simple_ws.py` | Cliente WebSocket mínimo para inspecionar a ingestão | `JORNADA_INFORMACAO_ESP32.md` |
| `testar_admin_adequado.py` | Percorre a página de administração | `docs/COMO_USAR_ADMIN.md` |
| `testar_reconciliacao_cama_id.py` | Verifica a reconciliação device→cama→paciente | `docs/ADMIN_PAGE_RECONCILIACAO.md` |
| `testar_simulacao_com_verificacao.py` | Simula um paciente e confere o resultado no banco | `preparar_demo.ps1`, `docs/GUIA_DEMONSTRACAO.md` |
| `ver_pacientes.py` | Lista os pacientes cadastrados | `preparar_demo.ps1`, `docs/GUIA_DEMONSTRACAO.md` |
| `verificar_pacientes.py` | Confere consistência das fichas de paciente | `preparar_demo.ps1` |

## Autenticação

As rotas de dados clínicos passaram a exigir sessão. Scripts que batem na API
precisam autenticar — via login (`POST /api/auth/login`, que devolve o cookie)
ou com um JWT no header `Authorization: Bearer`. Os que ingerem dados como se
fossem um ESP32 usam o header `X-Device-Token`, com o valor de
`UPP_DEVICE_TOKEN` (ver `.env.example`).

Alguns destes scripts foram escritos quando a API era aberta e podem precisar
desse ajuste no primeiro uso.
