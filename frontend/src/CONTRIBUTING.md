# Guia de Contribuição

## 🎯 Objetivo

Este documento orienta desenvolvedores que irão contribuir com o projeto Monitor de Alertas de Reposicionamento.

## 🏗️ Arquitetura

### Estrutura de Pastas

```
/
├── components/          # Componentes React
│   ├── auth/           # Autenticação
│   ├── layout/         # Layouts e navegação
│   ├── pages/          # Páginas principais
│   ├── alerts/         # Componentes de alertas
│   ├── patients/       # Componentes de pacientes
│   ├── shared/         # Componentes compartilhados
│   └── ui/             # Componentes UI base (shadcn)
├── hooks/              # Custom React hooks
├── lib/                # Utilitários e serviços
├── styles/             # CSS global e tokens
└── *.md                # Documentação
```

### Convenções de Nomenclatura

#### Arquivos
- Componentes: `PascalCase.tsx` (ex: `AlertsTable.tsx`)
- Hooks: `camelCase.ts` com prefixo `use` (ex: `useAuth.ts`)
- Utilitários: `camelCase.ts` (ex: `api.ts`)
- Tipos: co-localizados ou em `types.ts`

#### Código
- Componentes: `PascalCase`
- Funções: `camelCase`
- Constantes: `UPPER_SNAKE_CASE`
- Interfaces: `PascalCase` com sufixo descritivo (ex: `AlertsTableProps`)

## 📝 Padrões de Código

### TypeScript

**Sempre** usar TypeScript. Sem `any`.

```typescript
// ✅ Bom
interface User {
  username: string;
  displayName?: string;
}

function getUser(id: string): Promise<User> {
  // ...
}

// ❌ Ruim
function getUser(id: any): any {
  // ...
}
```

### Componentes React

#### Estrutura Padrão

```typescript
import { useState } from 'react';
import { Button } from '../ui/button';
import { SomeType } from './types';

interface ComponentNameProps {
  requiredProp: string;
  optionalProp?: number;
  onAction: (data: SomeType) => void;
}

export function ComponentName({
  requiredProp,
  optionalProp = 10,
  onAction,
}: ComponentNameProps) {
  const [state, setState] = useState<SomeType | null>(null);

  const handleClick = () => {
    // Lógica aqui
    onAction(data);
  };

  return (
    <div>
      {/* JSX aqui */}
    </div>
  );
}
```

#### Props Destructuring

Sempre desestruturar props no parâmetro da função:

```typescript
// ✅ Bom
function Component({ name, age }: Props) {
  return <div>{name}</div>;
}

// ❌ Ruim
function Component(props: Props) {
  return <div>{props.name}</div>;
}
```

#### Default Props

Usar destructuring com valores padrão:

```typescript
function Component({ 
  size = 'md', 
  variant = 'default' 
}: Props) {
  // ...
}
```

### Hooks

#### useEffect

Sempre declarar dependências corretamente:

```typescript
// ✅ Bom
useEffect(() => {
  fetchData(id);
}, [id]); // id na dependência

// ❌ Ruim
useEffect(() => {
  fetchData(id);
}, []); // eslint vai reclamar
```

#### Custom Hooks

Prefixar com `use` e retornar objeto:

```typescript
export function useCustomHook(param: string) {
  const [data, setData] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  // Lógica aqui

  return {
    data,
    isLoading,
    refetch: () => fetchData(),
  };
}
```

### Async/Await

Sempre usar try/catch para operações assíncronas:

```typescript
// ✅ Bom
const handleSubmit = async () => {
  try {
    await api.submit(data);
    toast.success('Sucesso');
  } catch (err) {
    if (err instanceof ApiException) {
      toast.error(err.message);
    } else {
      toast.error('Erro desconhecido');
    }
  }
};

// ❌ Ruim
const handleSubmit = async () => {
  await api.submit(data); // Sem tratamento de erro
  toast.success('Sucesso');
};
```

### Styling

#### Tailwind CSS

Usar classes Tailwind sempre que possível:

```tsx
// ✅ Bom
<div className="flex items-center gap-4 p-6">

// ❌ Ruim
<div style={{ display: 'flex', alignItems: 'center', gap: '16px', padding: '24px' }}>
```

#### Conditional Classes

Usar `cn()` utility:

```typescript
import { cn } from '../ui/utils';

<div className={cn(
  'base-classes',
  isActive && 'active-classes',
  error && 'error-classes'
)}>
```

#### Design Tokens

Usar tokens CSS em vez de valores hardcoded:

```tsx
// ✅ Bom
<div className="bg-primary text-primary-foreground">

// ❌ Ruim  
<div className="bg-[#0B5FFF] text-white">
```

### Acessibilidade

#### Labels

Sempre associar labels a inputs:

```tsx
// ✅ Bom
<div>
  <Label htmlFor="email">Email</Label>
  <Input id="email" type="email" />
</div>

// ❌ Ruim
<div>
  <span>Email</span>
  <Input type="email" />
</div>
```

#### Botões

Botões sem texto devem ter aria-label:

```tsx
// ✅ Bom
<Button aria-label="Fechar">
  <X className="w-4 h-4" />
</Button>

// ❌ Ruim
<Button>
  <X className="w-4 h-4" />
</Button>
```

#### Navegação por Teclado

Garantir que elementos interativos sejam focáveis:

```tsx
// ✅ Bom - Button nativo é focável
<Button onClick={handleClick}>Click</Button>

// ❌ Ruim - div não é focável por padrão
<div onClick={handleClick}>Click</div>
```

## 🧪 Testing (Futuro)

### Testes Unitários

Usar Vitest:

```typescript
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ComponentName } from './ComponentName';

describe('ComponentName', () => {
  it('renders correctly', () => {
    render(<ComponentName prop="value" />);
    expect(screen.getByText('Expected Text')).toBeInTheDocument();
  });

  it('handles click', async () => {
    const onClick = vi.fn();
    render(<ComponentName onClick={onClick} />);
    
    await userEvent.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});
```

### Testes de Integração

Para fluxos críticos:
- Login/Registro
- Criação de alertas
- Reposicionamento de pacientes

## 🔍 Code Review

### Checklist

Antes de submeter PR, verificar:

- [ ] Código segue convenções de nomenclatura
- [ ] TypeScript sem erros ou `any`
- [ ] Componentes têm tipos para props
- [ ] Não há console.logs
- [ ] Tratamento de erros implementado
- [ ] Loading states implementados
- [ ] Empty states implementados
- [ ] Responsivo (testar mobile e desktop)
- [ ] Acessível (tab navigation funciona)
- [ ] Sem warnings no console
- [ ] Comentários apenas onde necessário

### Pull Request

#### Título

Formato: `[Tipo] Descrição curta`

Tipos:
- `[Feature]` - Nova funcionalidade
- `[Fix]` - Correção de bug
- `[Refactor]` - Refatoração
- `[Docs]` - Documentação
- `[Style]` - Styling
- `[Test]` - Testes

Exemplos:
- `[Feature] Adiciona filtros na tabela de alertas`
- `[Fix] Corrige polling que não parava ao fazer logout`
- `[Refactor] Extrai lógica de autenticação para hook`

#### Descrição

```markdown
## O que mudou
Breve descrição das mudanças

## Por que
Motivo da mudança

## Como testar
1. Passo 1
2. Passo 2
3. Resultado esperado

## Screenshots (se aplicável)
[Imagens]

## Checklist
- [ ] Testado em Chrome
- [ ] Testado em Firefox
- [ ] Testado em mobile
- [ ] Sem erros no console
- [ ] Documentação atualizada (se necessário)
```

## 🐛 Debugging

### React DevTools

Instalar extensão do React DevTools no navegador.

### Console Logs

Para desenvolvimento, usar estruturado:

```typescript
// ✅ Bom
console.group('API Call');
console.log('Request:', requestData);
console.log('Response:', responseData);
console.groupEnd();

// Remover antes de commit
```

### Breakpoints

Usar `debugger;` statement ou breakpoints no DevTools.

## 📦 Adicionando Dependências

### Antes de Adicionar

Perguntar:
1. Essa lib é realmente necessária?
2. Existe alternativa nativa ou com Tailwind?
3. Qual o tamanho do bundle?
4. Está ativamente mantida?

### Como Adicionar

```bash
npm install package-name
```

Atualizar README.md se for dependência importante.

### Versões Específicas

Algumas libs precisam de versão específica (ver `/lib/api.ts`):

```typescript
// ✅ Bom
import { useForm } from 'react-hook-form@7.55.0';

// ❌ Ruim
import { useForm } from 'react-hook-form';
```

## 🎨 Design System

### Quando Criar Novo Componente

Criar em `/components/shared/` se:
- Reutilizado em 2+ lugares
- Lógica complexa
- Estados múltiplos (loading, error, success)

Manter inline se:
- Usado uma única vez
- Muito simples
- Específico de uma página

### Variantes

Usar pattern de variantes para flexibilidade:

```typescript
interface ButtonProps {
  variant?: 'default' | 'outline' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
}

const variants = {
  default: 'bg-primary text-primary-foreground',
  outline: 'border border-primary text-primary',
  ghost: 'hover:bg-muted',
};

const sizes = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-4 py-2',
  lg: 'px-6 py-3 text-lg',
};

<button className={cn(variants[variant], sizes[size])}>
```

## 🚀 Performance

### Otimizações

#### useMemo

Para computações caras:

```typescript
const sortedData = useMemo(() => {
  return heavyComputation(data);
}, [data]);
```

#### useCallback

Para funções passadas como props:

```typescript
const handleClick = useCallback(() => {
  doSomething(id);
}, [id]);
```

#### Lazy Loading

Para páginas/componentes grandes:

```typescript
const AdminPage = lazy(() => import('./components/pages/AdminPage'));
```

### Evitar

- Re-renders desnecessários
- Fetch de dados em loops
- Inline functions em props (usar useCallback)
- Keys ineficientes em listas

## 🔒 Segurança

### Nunca Commitar

- Tokens de API
- Senhas
- URLs de produção com credenciais
- .env files (usar .env.example)

### Input Sanitization

Backend deve sanitizar, mas frontend também deve validar:

```typescript
// Validar antes de enviar
if (!email.includes('@')) {
  setError('Email inválido');
  return;
}
```

### XSS Prevention

React já escapa strings automaticamente. Evitar:

```tsx
// ❌ Perigoso
<div dangerouslySetInnerHTML={{ __html: userInput }} />

// ✅ Seguro
<div>{userInput}</div>
```

## 📚 Recursos

### Documentação

- [React](https://react.dev/)
- [TypeScript](https://www.typescriptlang.org/docs/)
- [Tailwind CSS](https://tailwindcss.com/docs)
- [shadcn/ui](https://ui.shadcn.com/)
- [Vite](https://vitejs.dev/)

### Ferramentas

- [React DevTools](https://react.dev/learn/react-developer-tools)
- [TypeScript Playground](https://www.typescriptlang.org/play)
- [Tailwind Play](https://play.tailwindcss.com/)

## ❓ Perguntas Frequentes

### Como adicionar nova página?

1. Criar componente em `/components/pages/NewPage.tsx`
2. Adicionar rota em `App.tsx`
3. Adicionar link na sidebar (`/components/layout/AppLayout.tsx`)

### Como adicionar novo endpoint de API?

1. Adicionar tipos em `/lib/api.ts`
2. Criar função no objeto `api` apropriado
3. Usar nos componentes com try/catch

### Como estilizar um componente shadcn?

```typescript
// Extender com classes Tailwind
<Button className="custom-classes">

// Ou modificar o componente em /components/ui/
```

### Como debugar problema de autenticação?

1. Verificar console (erros de fetch)
2. Verificar Network tab (status codes)
3. Verificar Application tab (cookies)
4. Ver se backend está rodando

## 🤝 Suporte

**Dúvidas de código**: Abrir issue no repositório  
**Bugs**: Abrir issue com passos para reproduzir  
**Sugestões**: Abrir discussion ou issue

---

**Obrigado por contribuir!** 🎉
