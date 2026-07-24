# Exemplos de Uso

Este documento contém exemplos práticos de como usar os componentes e padrões do sistema.

## 📋 Índice

1. [Criando Nova Página](#criando-nova-página)
2. [Integrando com API](#integrando-com-api)
3. [Criando Formulário](#criando-formulário)
4. [Adicionando Estados de Loading](#adicionando-estados-de-loading)
5. [Tratando Erros](#tratando-erros)
6. [Usando Polling](#usando-polling)
7. [Criando Modal](#criando-modal)
8. [Tabela com Dados](#tabela-com-dados)
9. [Upload de Arquivo](#upload-de-arquivo)
10. [Notificações Toast](#notificações-toast)

---

## 1. Criando Nova Página

### Passo a Passo

**1. Criar componente da página**

```typescript
// /components/pages/ReportsPage.tsx
import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Download } from 'lucide-react';

export function ReportsPage() {
  const [reports, setReports] = useState([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Fetch reports
    setIsLoading(false);
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-foreground">Relatórios</h1>
          <p className="text-muted-foreground">
            Gerencie e exporte relatórios
          </p>
        </div>
        <Button>
          <Download className="w-4 h-4 mr-2" />
          Exportar
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Relatórios Disponíveis</CardTitle>
        </CardHeader>
        <CardContent>
          {/* Conteúdo aqui */}
        </CardContent>
      </Card>
    </div>
  );
}
```

**2. Adicionar no App.tsx**

```typescript
// App.tsx
import { ReportsPage } from './components/pages/ReportsPage';

type Page = 'dashboard' | 'timeline' | 'patients' | 'admin' | 'reports';

// No renderPage()
case 'reports':
  return <ReportsPage />;
```

**3. Adicionar na navegação**

```typescript
// /components/layout/AppLayout.tsx
import { FileText } from 'lucide-react';

const navigation = [
  // ... outros items
  { id: 'reports', name: 'Relatórios', icon: FileText },
];
```

---

## 2. Integrando com API

### Exemplo: Buscar Dados

```typescript
import { useEffect, useState } from 'react';
import { ApiException } from '../lib/api';
import { Spinner } from '../components/shared/Spinner';
import { ErrorBanner } from '../components/shared/ErrorBanner';

interface Report {
  id: string;
  name: string;
  createdAt: string;
}

export function ReportsPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchReports();
  }, []);

  const fetchReports = async () => {
    try {
      const response = await fetch('/api/reports', {
        credentials: 'same-origin',
      });
      
      if (!response.ok) {
        throw new Error('Erro ao buscar relatórios');
      }
      
      const data = await response.json();
      setReports(data);
      setError(null);
    } catch (err) {
      if (err instanceof ApiException) {
        setError(err.message);
      } else {
        setError('Erro desconhecido');
      }
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading) {
    return <Spinner />;
  }

  if (error) {
    return (
      <ErrorBanner
        message={error}
        onRetry={fetchReports}
      />
    );
  }

  return (
    <div>
      {reports.map(report => (
        <div key={report.id}>{report.name}</div>
      ))}
    </div>
  );
}
```

### Exemplo: Usar Cliente API

```typescript
// Primeiro, adicionar ao /lib/api.ts
export const reportsApi = {
  getReports: () => request<Report[]>('/api/reports'),
  
  generateReport: (type: string) =>
    request<Report>('/api/reports', {
      method: 'POST',
      body: JSON.stringify({ type }),
    }),
};

// Depois, usar no componente
import { reportsApi } from '../lib/api';

const fetchReports = async () => {
  try {
    const data = await reportsApi.getReports();
    setReports(data);
  } catch (err) {
    // tratamento
  }
};
```

---

## 3. Criando Formulário

### Formulário Simples

```typescript
import { useState } from 'react';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { toast } from 'sonner';

export function CreateReportForm() {
  const [formData, setFormData] = useState({
    title: '',
    type: 'monthly',
  });
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);

    try {
      await reportsApi.generateReport(formData);
      toast.success('Relatório gerado com sucesso');
      // Reset form ou redirect
    } catch (err) {
      toast.error('Erro ao gerar relatório');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="title">Título</Label>
        <Input
          id="title"
          value={formData.title}
          onChange={(e) =>
            setFormData({ ...formData, title: e.target.value })
          }
          required
        />
      </div>

      <Button type="submit" disabled={isSubmitting}>
        {isSubmitting ? 'Gerando...' : 'Gerar Relatório'}
      </Button>
    </form>
  );
}
```

### Formulário com Validação

```typescript
import { useState } from 'react';
import { Alert, AlertDescription } from '../ui/alert';
import { AlertCircle } from 'lucide-react';

export function CreateReportForm() {
  const [formData, setFormData] = useState({
    title: '',
    startDate: '',
    endDate: '',
  });
  const [errors, setErrors] = useState<Record<string, string>>({});

  const validate = () => {
    const newErrors: Record<string, string> = {};

    if (!formData.title.trim()) {
      newErrors.title = 'Título é obrigatório';
    }

    if (!formData.startDate) {
      newErrors.startDate = 'Data inicial é obrigatória';
    }

    if (!formData.endDate) {
      newErrors.endDate = 'Data final é obrigatória';
    }

    if (formData.startDate && formData.endDate) {
      if (new Date(formData.startDate) > new Date(formData.endDate)) {
        newErrors.endDate = 'Data final deve ser após data inicial';
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validate()) {
      return;
    }

    // Submit...
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {Object.keys(errors).length > 0 && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Por favor, corrija os erros no formulário
          </AlertDescription>
        </Alert>
      )}

      <div className="space-y-2">
        <Label htmlFor="title">Título</Label>
        <Input
          id="title"
          value={formData.title}
          onChange={(e) =>
            setFormData({ ...formData, title: e.target.value })
          }
          className={errors.title ? 'border-destructive' : ''}
        />
        {errors.title && (
          <p className="text-destructive">{errors.title}</p>
        )}
      </div>

      {/* Outros campos... */}
    </form>
  );
}
```

---

## 4. Adicionando Estados de Loading

### Skeleton Loading

```typescript
import { Skeleton } from '../ui/skeleton';

export function ReportsPage() {
  const [isLoading, setIsLoading] = useState(true);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="space-y-2">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-4 w-72" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
      </div>
    );
  }

  return <div>{/* Conteúdo real */}</div>;
}
```

### Loading Overlay

```typescript
import { LoadingOverlay } from '../components/shared/LoadingOverlay';

export function ReportCard() {
  const [isGenerating, setIsGenerating] = useState(false);

  return (
    <Card className="relative">
      {isGenerating && <LoadingOverlay message="Gerando relatório..." />}
      
      <CardContent>
        {/* Conteúdo */}
      </CardContent>
    </Card>
  );
}
```

### Botão com Loading

```typescript
import { Spinner } from '../components/shared/Spinner';

<Button disabled={isLoading}>
  {isLoading ? (
    <>
      <Spinner size="sm" className="mr-2" />
      Processando...
    </>
  ) : (
    'Enviar'
  )}
</Button>
```

---

## 5. Tratando Erros

### Banner de Erro

```typescript
import { ErrorBanner } from '../components/shared/ErrorBanner';

export function ReportsPage() {
  const [error, setError] = useState<string | null>(null);

  return (
    <div>
      {error && (
        <ErrorBanner
          message={error}
          onRetry={fetchData}
          onDismiss={() => setError(null)}
        />
      )}
      {/* Conteúdo */}
    </div>
  );
}
```

### Toast de Erro

```typescript
import { toast } from 'sonner';

const handleDelete = async (id: string) => {
  try {
    await api.delete(id);
    toast.success('Deletado com sucesso');
  } catch (err) {
    if (err instanceof ApiException) {
      toast.error(err.message);
    } else {
      toast.error('Erro ao deletar');
    }
  }
};
```

### Estado de Erro Offline

```typescript
const [isOffline, setIsOffline] = useState(false);

useEffect(() => {
  const handleOnline = () => setIsOffline(false);
  const handleOffline = () => setIsOffline(true);

  window.addEventListener('online', handleOnline);
  window.addEventListener('offline', handleOffline);

  return () => {
    window.removeEventListener('online', handleOnline);
    window.removeEventListener('offline', handleOffline);
  };
}, []);

if (isOffline) {
  return (
    <ErrorBanner
      type="offline"
      title="Sem conexão"
      message="Você está offline. Algumas funcionalidades podem não estar disponíveis."
    />
  );
}
```

---

## 6. Usando Polling

```typescript
import { usePolling } from '../hooks/usePolling';

export function LiveReportsPage() {
  const [reports, setReports] = useState([]);

  const fetchReports = useCallback(async () => {
    const data = await reportsApi.getReports();
    setReports(data);
  }, []);

  const { isPolling, toggle } = usePolling({
    interval: 30000, // 30 segundos
    enabled: true,
    onPoll: fetchReports,
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1>Relatórios em Tempo Real</h1>
        <PollIndicator
          isPolling={isPolling}
          interval={30000}
          onManualRefresh={fetchReports}
        />
      </div>
      {/* Lista de relatórios */}
    </div>
  );
}
```

---

## 7. Criando Modal

### Dialog Simples

```typescript
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '../ui/dialog';
import { Button } from '../ui/button';

export function ReportDetailsModal({ report }: { report: Report }) {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="outline">Ver Detalhes</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{report.title}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <p>Criado em: {report.createdAt}</p>
          <p>Status: {report.status}</p>
          {/* Mais conteúdo */}
        </div>
      </DialogContent>
    </Dialog>
  );
}
```

### AlertDialog para Confirmação

```typescript
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

export function DeleteConfirmDialog() {
  const [open, setOpen] = useState(false);

  const handleDelete = async () => {
    await api.delete(id);
    setOpen(false);
  };

  return (
    <>
      <Button variant="destructive" onClick={() => setOpen(true)}>
        Deletar
      </Button>

      <AlertDialog open={open} onOpenChange={setOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Confirmar Exclusão</AlertDialogTitle>
            <AlertDialogDescription>
              Esta ação não pode ser desfeita. O relatório será permanentemente removido.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>
              Confirmar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
```

---

## 8. Tabela com Dados

```typescript
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../ui/table';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';

interface Report {
  id: string;
  title: string;
  status: 'pending' | 'completed' | 'failed';
  createdAt: string;
}

export function ReportsTable({ reports }: { reports: Report[] }) {
  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return <Badge className="bg-success text-success-foreground">Completo</Badge>;
      case 'pending':
        return <Badge className="bg-warning text-warning-foreground">Pendente</Badge>;
      case 'failed':
        return <Badge variant="destructive">Falhou</Badge>;
    }
  };

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Título</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Criado em</TableHead>
            <TableHead>Ações</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {reports.map((report) => (
            <TableRow key={report.id}>
              <TableCell>{report.title}</TableCell>
              <TableCell>{getStatusBadge(report.status)}</TableCell>
              <TableCell>
                {new Date(report.createdAt).toLocaleDateString('pt-BR')}
              </TableCell>
              <TableCell>
                <Button size="sm" variant="outline">
                  Ver
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
```

---

## 9. Upload de Arquivo

```typescript
import { useState } from 'react';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Button } from '../ui/button';
import { Upload } from 'lucide-react';

export function FileUploadForm() {
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const handleUpload = async () => {
    if (!file) return;

    setIsUploading(true);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
        credentials: 'same-origin',
      });

      if (!response.ok) throw new Error('Upload falhou');

      toast.success('Arquivo enviado com sucesso');
      setFile(null);
    } catch (err) {
      toast.error('Erro ao enviar arquivo');
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="file">Selecione o arquivo</Label>
        <Input
          id="file"
          type="file"
          onChange={handleFileChange}
          accept=".pdf,.jpg,.png"
        />
        {file && (
          <p className="text-muted-foreground">
            Arquivo selecionado: {file.name}
          </p>
        )}
      </div>

      <Button onClick={handleUpload} disabled={!file || isUploading}>
        {isUploading ? (
          <>
            <Spinner size="sm" className="mr-2" />
            Enviando...
          </>
        ) : (
          <>
            <Upload className="w-4 h-4 mr-2" />
            Enviar
          </>
        )}
      </Button>
    </div>
  );
}
```

---

## 10. Notificações Toast

### Toast Simples

```typescript
import { toast } from 'sonner';

// Sucesso
toast.success('Operação concluída');

// Erro
toast.error('Algo deu errado');

// Info
toast.info('Nova atualização disponível');

// Warning
toast.warning('Atenção necessária');
```

### Toast com Ação

```typescript
toast.success('Item deletado', {
  action: {
    label: 'Desfazer',
    onClick: () => handleUndo(),
  },
});
```

### Toast Customizado

```typescript
toast.custom((t) => (
  <div className="bg-surface border rounded-lg p-4 shadow-lg">
    <h4 className="font-medium">Título Customizado</h4>
    <p className="text-muted-foreground">Descrição aqui</p>
    <Button size="sm" onClick={() => toast.dismiss(t)}>
      Fechar
    </Button>
  </div>
));
```

### Toast Persistente

```typescript
const toastId = toast.loading('Processando...', {
  duration: Infinity,
});

// Depois atualizar
toast.success('Concluído!', { id: toastId });
```

---

## 🎯 Padrões Avançados

### Optimistic Updates

```typescript
const handleComplete = async (id: string) => {
  // 1. Update UI imediatamente
  setReports((prev) =>
    prev.map((r) => (r.id === id ? { ...r, status: 'completed' } : r))
  );

  try {
    // 2. Chamar API
    await reportsApi.complete(id);
    toast.success('Relatório concluído');
  } catch (err) {
    // 3. Reverter em caso de erro
    fetchReports();
    toast.error('Erro ao concluir');
  }
};
```

### Debounced Search

```typescript
import { useState, useEffect } from 'react';
import { Input } from '../ui/input';

export function SearchReports() {
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
    }, 500);

    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    if (debouncedSearch) {
      // Fazer busca
      searchReports(debouncedSearch);
    }
  }, [debouncedSearch]);

  return (
    <Input
      placeholder="Buscar..."
      value={search}
      onChange={(e) => setSearch(e.target.value)}
    />
  );
}
```

### Infinite Scroll

```typescript
import { useEffect, useRef } from 'react';

export function InfiniteReportsList() {
  const [reports, setReports] = useState([]);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const loaderRef = useRef(null);

  useEffect(() => {
    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting && hasMore) {
        setPage((prev) => prev + 1);
      }
    });

    if (loaderRef.current) {
      observer.observe(loaderRef.current);
    }

    return () => observer.disconnect();
  }, [hasMore]);

  useEffect(() => {
    fetchReports(page);
  }, [page]);

  return (
    <div>
      {reports.map((report) => (
        <ReportCard key={report.id} report={report} />
      ))}
      {hasMore && <div ref={loaderRef}>Carregando...</div>}
    </div>
  );
}
```

---

## 💡 Dicas

### Performance

```typescript
// ✅ Bom - Memoizar computações caras
const sortedReports = useMemo(() => {
  return reports.sort((a, b) => 
    new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
  );
}, [reports]);

// ✅ Bom - useCallback para funções em deps
const handleClick = useCallback(() => {
  doSomething(id);
}, [id]);
```

### Acessibilidade

```typescript
// ✅ Bom - Aria labels e roles
<button
  aria-label="Fechar modal"
  role="button"
  onClick={handleClose}
>
  <X />
</button>

// ✅ Bom - Focus management
useEffect(() => {
  if (isOpen) {
    inputRef.current?.focus();
  }
}, [isOpen]);
```

### TypeScript

```typescript
// ✅ Bom - Tipos específicos
type Status = 'pending' | 'completed' | 'failed';

interface Report {
  id: string;
  status: Status;
}

// ❌ Ruim - any
interface Report {
  data: any;
}
```

---

Estes exemplos cobrem os casos de uso mais comuns. Para mais detalhes, consulte a documentação específica de cada biblioteca.
