# Guia Visual - Monitor de Alertas de Reposicionamento

Este documento fornece uma referência visual da aplicação, descrevendo cada tela e seus componentes.

## 🎨 Paleta de Cores

```
Primária (Azul):    ████ #0B5FFF - Ações, links, elementos interativos
Sucesso (Verde):    ████ #10B981 - Confirmações, completado
Alerta (Amarelo):   ████ #FBBF24 - Avisos, reconhecido
Perigo (Vermelho):  ████ #EF4444 - Crítico, erro, exclusão

Background:         ████ #F8FAFC - Fundo da app
Surface:            ████ #FFFFFF - Cards, modais
Texto Principal:    ████ #0F172A - Texto primário
Texto Secundário:   ████ #64748B - Texto auxiliar
Bordas:             ████ #E2E8F0 - Divisórias
```

---

## 📱 Telas da Aplicação

### 1. Login / Registro

#### Login
```
┌─────────────────────────────────────────┐
│                                         │
│            [Ícone Coração]              │
│                                         │
│   Sistema de Alertas de                 │
│   Reposicionamento                      │
│                                         │
│   Gestão de pacientes com risco de     │
│   úlcera de pressão                     │
│                                         │
│   ┌───────────────────────────────┐    │
│   │ Usuário                       │    │
│   │ [___________________]         │    │
│   │                               │    │
│   │ Senha                         │    │
│   │ [___________________]         │    │
│   │                               │    │
│   │  [ Entrar ]                   │    │
│   │                               │    │
│   │  Não tem conta? Criar conta   │    │
│   └───────────────────────────────┘    │
│                                         │
└─────────────────────────────────────────┘
```

**Elementos:**
- Card central com sombra
- Ícone de coração em círculo azul claro
- Campos de input com labels
- Botão primário azul
- Link para registro

#### Registro
```
┌─────────────────────────────────────────┐
│   Criar Conta                           │
│   Cadastre-se para acessar o sistema   │
│                                         │
│   Nome Completo                         │
│   [___________________________]         │
│                                         │
│   Usuário                               │
│   [___________________________]         │
│                                         │
│   Senha                                 │
│   [___________________________]         │
│                                         │
│   Confirmar Senha                       │
│   [___________________________]         │
│                                         │
│   [ Criar conta ]                       │
│                                         │
│   Já tem conta? Entrar                  │
└─────────────────────────────────────────┘
```

**Elementos:**
- Mesmo layout do login
- Campos adicionais (nome, confirmação)
- Validação em tempo real

---

### 2. Dashboard

```
┌────────────────────────────────────────────────────────────────┐
│ [☰] Alertas                                    Alice  [Sair]   │ Header
├────┬───────────────────────────────────────────────────────────┤
│    │ Dashboard                                                 │
│ [□]│ Monitor de alertas de reposicionamento                   │
│ D  │                                                           │
│ a  │ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐    │
│ s  │ │ [Bell]   │ │ [!]      │ │ [Cal]    │ │ [✓]      │    │
│ h  │ │ Alertas  │ │ Atrasa-  │ │ Reconhe- │ │ Taxa     │    │
│    │ │ Ativos   │ │ dos      │ │ cidos    │ │ Sucesso  │    │
│ [H]│ │ 5        │ │ 2        │ │ 1        │ │ 85%      │    │
│ i  │ └──────────┘ └──────────┘ └──────────┘ └──────────┘    │
│ s  │                                                           │
│ t  │ ┌─────────────────────────────────────────────────────┐  │
│    │ │ Alertas Ativos                    🔄 Atualiza 30s  │  │
│ [P]│ ├─────────────────────────────────────────────────────┤  │
│ a  │ │ Paciente  │Quarto│Risco │Último│Próximo│Status│Ações│  │
│ c  │ ├─────────────────────────────────────────────────────┤  │
│ i  │ │[!] Maria  │201A  │Alto  │13:00 │15:00  │Pend. │[R][C]│  │
│ e  │ │    Silva  │L1    │Risk  │      │ATRASO │      │      │  │
│ n  │ ├─────────────────────────────────────────────────────┤  │
│    │ │    João   │203B  │Médio │14:00 │16:00  │Recon.│  [C]│  │
│ [A]│ │    Santos │L2    │Risk  │      │Em 1h  │      │      │  │
│ d  │ └─────────────────────────────────────────────────────┘  │
│ m  │                                                           │
│ i  │                                                           │
│ n  │                                                           │
└────┴───────────────────────────────────────────────────────────┘
   Sidebar                     Main Content
```

**Componentes:**
1. **Header Mobile**: Menu hambúrguer + título
2. **Sidebar Desktop**: Navegação vertical (Dashboard, Histórico, Pacientes, Admin)
3. **Stats Cards**: 4 cards com métricas principais
4. **Poll Indicator**: Ícone de refresh + countdown
5. **Alerts Table**: Tabela com alertas ordenados por prioridade
6. **Action Buttons**: Reconhecer (outline) + Reposicionar (primary)

**Estados:**
- Linha vermelha clara: Alerta atrasado
- Badge vermelho: Alto risco
- Badge amarelo: Risco médio
- Badge azul: Reconhecido
- Ícone de alerta (!) em alertas atrasados

---

### 3. Timeline / Histórico

```
┌────────────────────────────────────────────────────────────────┐
│ Histórico de Eventos                                           │
│ Timeline de alertas e reposicionamentos                        │
│                                                                 │
│ ┌───────────────────────────────────────────────────────────┐ │
│ │ 25 de outubro de 2025                                     │ │
│ ├───────────────────────────────────────────────────────────┤ │
│ │                                                           │ │
│ │  ●  Paciente reposicionado          [Completo]  2h atrás │ │
│ │  │  Maria Silva - Quarto 201A                            │ │
│ │  │  25/10/2025 15:30 • Por: Enf. Ana                     │ │
│ │  │                                                        │ │
│ │  ●  Alerta reconhecido         [Reconhecido]  3h atrás   │ │
│ │  │  João Santos - Quarto 203B                            │ │
│ │  │  25/10/2025 14:45 • Por: Cuidador João                │ │
│ │  │                                                        │ │
│ │  ●  Alerta criado                 [Alerta]  4h atrás     │ │
│ │     Paciente ID: PAC-0001                                │ │
│ │     25/10/2025 13:30                                     │ │
│ │                                                           │ │
│ └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│ ┌───────────────────────────────────────────────────────────┐ │
│ │ 24 de outubro de 2025                                     │ │
│ ├───────────────────────────────────────────────────────────┤ │
│ │  ...                                                      │ │
│ └───────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
```

**Componentes:**
- Cards agrupados por dia
- Timeline vertical com conectores
- Ícones coloridos por tipo de evento:
  - ✓ Verde: Reposicionado
  - 👁 Azul: Reconhecido
  - ⚠ Amarelo: Alerta criado
- Badges coloridos
- Timestamps formatados
- Tempo relativo

---

### 4. Pacientes

#### Lista de Pacientes

```
┌────────────────────────────────────────────────────────────────┐
│ Pacientes                                    [+ Novo Paciente] │
│ Gerenciar pacientes e níveis de risco                         │
│                                                                 │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐           │
│ │ Maria Silva  │ │ João Santos  │ │ Ana Costa    │           │
│ │ [Alto Risco] │ │ [Risco Médio]│ │ [Baixo Risco]│           │
│ │              │ │              │ │              │           │
│ │ Quarto: 201A │ │ Quarto: 203B │ │ Quarto: 205A │           │
│ │ Leito: 1     │ │ Leito: 2     │ │ Leito: 1     │           │
│ │ Intervalo:2h │ │ Intervalo:3h │ │ Intervalo:4h │           │
│ │              │ │              │ │              │           │
│ │ [Editar] [🗑]│ │ [Editar] [🗑]│ │ [Editar] [🗑]│           │
│ └──────────────┘ └──────────────┘ └──────────────┘           │
└────────────────────────────────────────────────────────────────┘
```

**Componentes:**
- Grid responsivo de cards
- Badge de risco colorido no topo
- Informações do paciente
- Botões de ação (Editar + Deletar)

#### Formulário de Paciente

```
┌────────────────────────────────────────────────────────────────┐
│ Novo Paciente                                      [Cancelar]  │
│ Preencha as informações do paciente                           │
│                                                                 │
│ ┌───────────────────────────────────────────────────────────┐ │
│ │                                                           │ │
│ │  Nome Completo *                                          │ │
│ │  [_________________________________________________]      │ │
│ │                                                           │ │
│ │  Quarto *              Leito *                            │ │
│ │  [_________]           [_________]                        │ │
│ │                                                           │ │
│ │  Nível de Risco *                                         │ │
│ │  [▼ Risco Médio      ]                                    │ │
│ │                                                           │ │
│ │  Intervalo de Reposicionamento (horas) *                  │ │
│ │  [2____]                                                  │ │
│ │  Tempo entre cada reposicionamento                        │ │
│ │                                                           │ │
│ │  [ Criar Paciente ]  [Cancelar]                           │ │
│ │                                                           │ │
│ └───────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
```

**Componentes:**
- Card com formulário
- Labels com asterisco para campos obrigatórios
- Grid de 2 colunas para Quarto/Leito
- Select para nível de risco
- Input numérico para intervalo
- Texto de ajuda
- Botões de ação

---

### 5. Admin

```
┌────────────────────────────────────────────────────────────────┐
│ Administração                    [🔄 Atualizar][✓ Reconciliar] │
│ Gerenciar eventos de dispositivos e reconciliação             │
│                                                                 │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐           │
│ │ [⏱]         │ │ [✓]          │ │ [⚙]          │           │
│ │ Eventos     │ │ Eventos      │ │ Total de     │           │
│ │ Pendentes   │ │ Processados  │ │ Eventos      │           │
│ │ 3           │ │ 15           │ │ 18           │           │
│ └──────────────┘ └──────────────┘ └──────────────┘           │
│                                                                 │
│ ┌───────────────────────────────────────────────────────────┐ │
│ │ Eventos de Dispositivos                                   │ │
│ ├───────────────────────────────────────────────────────────┤ │
│ │ ID│Dispositivo│Tipo    │Dados     │Criado    │Status  │...│ │
│ ├───────────────────────────────────────────────────────────┤ │
│ │ 1 │sensor-001 │motion  │{"int...  │25/10 15:│[Pend.] │...│ │
│ │ 2 │sensor-002 │pressure│{"val...  │25/10 14:│[Proc.] │...│ │
│ │ 3 │sensor-001 │motion  │{"int...  │25/10 13:│[Pend.] │...│ │
│ └───────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────┘
```

**Componentes:**
- Stats cards específicos para admin
- Botões de ação no header (Atualizar, Reconciliar)
- Tabela com eventos de dispositivos
- Badges de status (Pendente em amarelo, Processado em verde)
- Dados JSON truncados

---

## 🎭 Estados dos Componentes

### Loading States

#### Skeleton
```
┌────────────────────────┐
│ ████████░░░░░░░░░░░░░  │  <- Título (animado)
│ ████░░░░░░░░░░░░░░░░░  │  <- Subtítulo (animado)
│                        │
│ ██████  ██████  ██████ │  <- Cards (animado)
│ ██████  ██████  ██████ │
└────────────────────────┘
```

#### Spinner
```
  ⟳  Carregando...
```

#### Button Loading
```
[ ⟳ Processando... ]  <- Desabilitado + spinner
```

### Empty States

```
┌────────────────────────────────┐
│                                │
│        ┌──────────┐            │
│        │  [Ícone] │            │
│        └──────────┘            │
│                                │
│     Nenhum dado encontrado     │
│                                │
│  Descrição explicativa aqui    │
│                                │
│      [ Ação Primária ]         │
│                                │
└────────────────────────────────┘
```

### Error States

#### Banner
```
┌─────────────────────────────────────────────────┐
│ [!] Erro                              [X] [🔄] │
│ Descrição do erro aqui                         │
└─────────────────────────────────────────────────┘
```

#### Inline Form Error
```
Email *
[________________________]  <- Borda vermelha
Email inválido              <- Texto vermelho
```

---

## 🔔 Notificações (Toasts)

### Sucesso
```
┌────────────────────────────┐
│ ✓ Operação concluída       │  <- Verde
└────────────────────────────┘
```

### Erro
```
┌────────────────────────────┐
│ ✗ Algo deu errado          │  <- Vermelho
└────────────────────────────┘
```

### Com Ação
```
┌──────────────────────────────────┐
│ ✓ Item deletado   [Desfazer]    │
└──────────────────────────────────┘
```

---

## 🎨 Componentes Reutilizáveis

### Button Variants

```
[ Primary ]        <- Azul sólido, texto branco
[ Outline ]        <- Borda azul, texto azul
[ Ghost ]          <- Sem borda, hover cinza
[ Destructive ]    <- Vermelho sólido, texto branco
```

### Badge Variants

```
[Default]  [Secondary]  [Outline]  [Destructive]
  Azul      Cinza        Borda       Vermelho
```

### Input States

```
Normal:     [___________________]
Focused:    [═══════════════════]  <- Borda azul
Error:      [___________________]  <- Borda vermelha
Disabled:   [───────────────────]  <- Cinza
```

---

## 📐 Espaçamento e Grid

### Grid Responsivo

```
Mobile (< 768px):
┌─────────────┐
│  Card 1     │
├─────────────┤
│  Card 2     │
├─────────────┤
│  Card 3     │
└─────────────┘

Tablet (768-1024px):
┌──────┬──────┐
│ Card │ Card │
├──────┼──────┤
│ Card │ ...  │
└──────┴──────┘

Desktop (> 1024px):
┌────┬────┬────┬────┐
│ C1 │ C2 │ C3 │ C4 │
└────┴────┴────┴────┘
```

### Espaçamento Padrão

```
Entre seções:      24px (space-6)
Entre cards:       16px (space-4)
Dentro de cards:   24px (p-6)
Entre elementos:   12px (space-3)
Dentro de botões:  12px 16px (py-3 px-4)
```

---

## 🎯 Iconografia

Todos os ícones usam Lucide React:

- **Navegação**: Bell, Users, LayoutDashboard, History, Settings
- **Ações**: Plus, Edit, Trash2, CheckCircle2, Eye, X
- **Status**: AlertTriangle, Clock, CheckCircle, WifiOff
- **UI**: Menu, LogOut, RefreshCw, Download, Upload

**Tamanhos padrão**:
- Pequeno: 16px (w-4 h-4)
- Médio: 20px (w-5 h-5)
- Grande: 24px (w-6 h-6)

---

Este guia visual serve como referência rápida para entender a estrutura e aparência da aplicação sem precisar rodar o código.
