# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/lang/pt-BR/).

## [1.0.0] - 2025-10-26

### ✨ Adicionado

#### Autenticação
- Sistema completo de login e registro
- Sessão persistente com cookies HttpOnly
- Hook `useAuth` para gerenciamento de autenticação
- Tela de login com validação de formulário
- Tela de registro com confirmação de senha
- Logout seguro

#### Dashboard
- Página principal com estatísticas
- Cards de métricas (alertas ativos, atrasados, reconhecidos, taxa de sucesso)
- Tabela de alertas com ordenação por prioridade
- Ações rápidas: Reconhecer e Reposicionar alertas
- Polling automático a cada 30 segundos
- Indicador de atualização em tempo real
- Confirmação antes de reposicionar paciente

#### Gestão de Pacientes
- Listagem de pacientes em cards responsivos
- Formulário de criação de paciente
- Formulário de edição de paciente
- Exclusão com confirmação
- Campos: nome, quarto, leito, nível de risco, intervalo de reposicionamento
- Validação de formulário

#### Timeline/Histórico
- Visualização cronológica de eventos
- Agrupamento de eventos por data
- Ícones e badges por tipo de evento
- Timestamps formatados
- Indicador de tempo relativo ("X horas atrás")

#### Administração
- Listagem de eventos de dispositivos IoT
- Visualização de eventos pendentes vs processados
- Botão de reconciliação manual
- Estatísticas de eventos (pendentes, processados, total)
- Exibição de dados brutos de eventos

#### Layout e Navegação
- Sidebar responsiva com navegação
- Menu hambúrguer em mobile
- Topbar com informações do usuário
- Layout adaptativo (mobile/tablet/desktop)
- Navegação por teclado completa

#### Componentes Compartilhados
- `Spinner`: Indicador de carregamento (sm/md/lg)
- `EmptyState`: Estado vazio com ícone, título e ação
- `ErrorBanner`: Banner de erro com retry e dismiss
- `LoadingOverlay`: Overlay de carregamento
- `PollIndicator`: Indicador de polling com countdown

#### Componentes UI (shadcn/ui)
- 40+ componentes base configurados
- Button com variantes e tamanhos
- Input com estados
- Card para containers
- Table responsiva
- Badge com cores customizadas
- Alert para mensagens
- Dialog e AlertDialog para modais
- Skeleton para loading states
- Toast (Sonner) para notificações

#### Hooks Customizados
- `useAuth`: Gerenciamento de autenticação
- `usePolling`: Polling configurável com controles

#### API Client
- Cliente API completo em `/lib/api.ts`
- Tratamento de erros com `ApiException`
- Tipos TypeScript para todos os endpoints
- Suporte a cookies `same-origin`
- Métodos para: auth, alerts, timeline, patients, device events

#### Design System
- Tokens CSS completos em `/styles/globals.css`
- Cores: primary, success, warning, danger, neutrals
- Espaçamento: 6 níveis (4px a 32px)
- Raios de borda: 4 níveis
- Paleta de cores acessível (WCAG AA)
- Tipografia Inter configurada

#### Documentação
- `INDEX.md`: Índice central da documentação
- `README.md`: Documentação principal do projeto
- `HANDOFF.md`: Guia completo de handoff
- `CONTRIBUTING.md`: Guia de contribuição
- `EXAMPLES.md`: Exemplos práticos de código
- `API_GAPS.md`: Gaps e melhorias de API
- `SUMMARY.md`: Resumo executivo
- `CHANGELOG.md`: Este arquivo

#### Configuração
- `vite.config.example.ts`: Exemplo de configuração do Vite
- `.env.example`: Exemplo de variáveis de ambiente
- `.gitignore.example`: Exemplo de gitignore
- `.vscode/settings.json.example`: Configurações VS Code
- `.vscode/extensions.json.example`: Extensões recomendadas

### 🎨 Design

- Interface clean e profissional adequada ao ambiente hospitalar
- Design responsivo (mobile-first)
- Acessibilidade WCAG 2.1 Level AA
- Navegação por teclado completa
- Screen reader friendly
- Contraste apropriado em todos os elementos

### 🔧 Técnico

- TypeScript strict mode
- React 18 com hooks
- Vite para build otimizado
- Tailwind CSS 4.0
- Code splitting por página
- Lazy loading preparado
- Optimistic updates em ações
- Debouncing preparado para buscas

### 📱 UX/UI

- Loading states em todas as operações
- Empty states em listas vazias
- Error states com opção de retry
- Confirmações para ações destrutivas
- Toast notifications para feedback
- Optimistic updates para melhor percepção de performance
- Skeleton loaders durante carregamento

### ♿ Acessibilidade

- Todos os inputs têm labels associados
- Botões sem texto têm aria-label
- Navegação por teclado funciona em toda a aplicação
- Modais podem ser fechados com ESC
- Foco visível em elementos interativos
- Contraste WCAG AA em textos e elementos interativos
- Atributos ARIA apropriados

### 🔐 Segurança

- Cookies HttpOnly para sessão
- Sanitização de inputs
- Proteção XSS (React automático)
- Validação client-side de formulários
- CORS configurável via proxy

---

## [Não Lançado]

### 🎯 Planejado

#### Alta Prioridade
- [ ] Integração com API backend real
- [ ] Testes de integração
- [ ] Testes unitários com Vitest
- [ ] Deploy em ambiente de staging
- [ ] Logs e monitoramento

#### Média Prioridade
- [ ] WebSocket para alertas em tempo real
- [ ] Notificações push
- [ ] Filtros avançados de alertas
- [ ] Busca de pacientes
- [ ] Paginação de listas grandes
- [ ] Exportação de relatórios (PDF/CSV)

#### Baixa Prioridade
- [ ] Upload de documentos de pacientes
- [ ] Modo offline (PWA)
- [ ] Configurações de usuário
- [ ] Tema dark mode
- [ ] Multi-idioma (i18n)
- [ ] Gráficos e dashboards avançados

### 🐛 Conhecido

Nenhum bug conhecido no momento.

### 🔄 Em Consideração

- Analytics de uso
- Audit log completo
- Sistema de permissões por role
- Notificações por email
- Integração com sistemas hospitalares existentes
- API GraphQL como alternativa

---

## Tipos de Mudanças

- `Adicionado` para novas funcionalidades
- `Alterado` para mudanças em funcionalidades existentes
- `Descontinuado` para funcionalidades que serão removidas
- `Removido` para funcionalidades removidas
- `Corrigido` para correções de bugs
- `Segurança` para vulnerabilidades

---

## Como Contribuir com o Changelog

Ao adicionar uma nova feature ou corrigir um bug:

1. Adicionar entrada na seção `[Não Lançado]`
2. Usar o formato: `- Descrição breve (#PR ou #Issue)`
3. Categorizar corretamente (Adicionado, Corrigido, etc.)
4. Ao fazer release, mover para nova versão com data

Exemplo:
```markdown
## [Não Lançado]

### Adicionado
- Filtro de alertas por nível de risco (#123)
- Busca de pacientes por nome (#124)

### Corrigido
- Polling não parava ao fazer logout (#125)
```

---

**Versionamento**: Usamos [Semantic Versioning](https://semver.org/):
- **MAJOR**: Mudanças incompatíveis na API
- **MINOR**: Novas funcionalidades compatíveis
- **PATCH**: Correções de bugs compatíveis
