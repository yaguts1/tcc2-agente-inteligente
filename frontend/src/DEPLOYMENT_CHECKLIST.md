# Checklist de Deploy - Monitor de Alertas

Use este checklist antes de fazer deploy em staging ou produção.

## 📋 Pre-Deploy Checklist

### Ambiente de Desenvolvimento

- [ ] **Código atualizado**
  - [ ] Todas as mudanças commitadas
  - [ ] Branch principal atualizada
  - [ ] Sem conflitos de merge

- [ ] **Dependências**
  - [ ] `npm install` executado sem erros
  - [ ] Versões de pacotes atualizadas
  - [ ] Vulnerabilidades de segurança resolvidas (`npm audit`)

- [ ] **Linting e Formatting**
  - [ ] Sem erros de TypeScript (`npm run type-check` ou similar)
  - [ ] Código formatado (Prettier)
  - [ ] Sem warnings no console do browser

- [ ] **Build Local**
  - [ ] `npm run build` executa sem erros
  - [ ] `npm run preview` funciona corretamente
  - [ ] Tamanho do bundle aceitável (< 500KB inicial)

---

## 🔧 Configuração de Ambiente

### Staging

- [ ] **Variáveis de Ambiente**
  - [ ] `.env.staging` configurado
  - [ ] `VITE_API_BASE_URL` aponta para backend de staging
  - [ ] `VITE_ENV=staging`

- [ ] **Backend**
  - [ ] API de staging está funcionando
  - [ ] Endpoints testados manualmente (Postman/curl)
  - [ ] CORS configurado para aceitar frontend de staging

- [ ] **Proxy/NGINX**
  - [ ] Configuração de proxy testada
  - [ ] Certificados SSL configurados (se HTTPS)
  - [ ] Redirecionamentos funcionando

### Produção

- [ ] **Variáveis de Ambiente**
  - [ ] `.env.production` configurado
  - [ ] `VITE_API_BASE_URL` aponta para backend de produção
  - [ ] `VITE_ENV=production`
  - [ ] Variáveis sensíveis armazenadas de forma segura

- [ ] **Backend**
  - [ ] API de produção está funcionando
  - [ ] Rate limiting configurado
  - [ ] Monitoramento ativo
  - [ ] Backups configurados

- [ ] **CDN/Hosting**
  - [ ] CDN configurado (se aplicável)
  - [ ] Cache configurado corretamente
  - [ ] Gzip/Brotli compressão ativa

---

## 🧪 Testes

### Testes Manuais

- [ ] **Autenticação**
  - [ ] Login com credenciais válidas
  - [ ] Login com credenciais inválidas (erro esperado)
  - [ ] Registro de novo usuário
  - [ ] Logout
  - [ ] Sessão persiste após refresh
  - [ ] Redirecionamento após logout

- [ ] **Dashboard**
  - [ ] Estatísticas carregam corretamente
  - [ ] Tabela de alertas exibe dados
  - [ ] Ordenação de alertas funciona
  - [ ] Reconhecer alerta funciona
  - [ ] Reposicionar paciente funciona
  - [ ] Confirmação de reposicionamento aparece
  - [ ] Polling automático funciona
  - [ ] Refresh manual funciona

- [ ] **Pacientes**
  - [ ] Lista de pacientes carrega
  - [ ] Criar novo paciente funciona
  - [ ] Editar paciente funciona
  - [ ] Excluir paciente funciona
  - [ ] Confirmação de exclusão aparece
  - [ ] Validação de formulário funciona

- [ ] **Timeline**
  - [ ] Eventos carregam
  - [ ] Agrupamento por data funciona
  - [ ] Timestamps estão corretos
  - [ ] Ícones e badges aparecem

- [ ] **Admin**
  - [ ] Eventos de dispositivos carregam
  - [ ] Reconciliação funciona
  - [ ] Estatísticas corretas

- [ ] **Layout/Navegação**
  - [ ] Sidebar funciona em desktop
  - [ ] Menu mobile funciona
  - [ ] Navegação entre páginas funciona
  - [ ] Informações do usuário aparecem

### Testes de Responsividade

- [ ] **Mobile (< 768px)**
  - [ ] Menu hambúrguer funciona
  - [ ] Tabelas scrollam horizontalmente
  - [ ] Cards em coluna única
  - [ ] Botões acessíveis
  - [ ] Formulários usáveis

- [ ] **Tablet (768px - 1024px)**
  - [ ] Layout apropriado
  - [ ] Sidebar comportamento correto
  - [ ] Grid de cards responsivo

- [ ] **Desktop (> 1024px)**
  - [ ] Sidebar fixa
  - [ ] Layout otimizado
  - [ ] Todos os elementos visíveis

### Testes Cross-Browser

- [ ] **Chrome** (última versão)
- [ ] **Firefox** (última versão)
- [ ] **Safari** (última versão, se Mac disponível)
- [ ] **Edge** (última versão)

### Testes de Performance

- [ ] **Lighthouse**
  - [ ] Performance: > 80
  - [ ] Accessibility: > 90
  - [ ] Best Practices: > 90
  - [ ] SEO: > 80 (se aplicável)

- [ ] **Loading Times**
  - [ ] First Contentful Paint < 2s
  - [ ] Time to Interactive < 3s
  - [ ] Largest Contentful Paint < 2.5s

- [ ] **Rede**
  - [ ] Funciona em 3G lento
  - [ ] Assets são cached
  - [ ] Sem requests desnecessários

### Testes de Erro

- [ ] **Estados de Erro**
  - [ ] Erro 401 redireciona para login
  - [ ] Erro 500 mostra mensagem apropriada
  - [ ] Erro de rede mostra banner offline
  - [ ] Retry funciona após erro

- [ ] **Validação**
  - [ ] Formulários validam campos obrigatórios
  - [ ] Mensagens de erro são claras
  - [ ] Validação client-side funciona

---

## 🔐 Segurança

- [ ] **Autenticação**
  - [ ] Cookies são HttpOnly
  - [ ] Sessões expiram apropriadamente
  - [ ] Logout limpa sessão completamente

- [ ] **Dados**
  - [ ] Inputs são sanitizados
  - [ ] Sem dados sensíveis em console
  - [ ] Sem dados sensíveis em URLs

- [ ] **HTTPS**
  - [ ] Certificado SSL válido
  - [ ] Redirecionamento HTTP → HTTPS
  - [ ] HSTS configurado (produção)

- [ ] **Headers de Segurança**
  - [ ] Content-Security-Policy configurado
  - [ ] X-Frame-Options configurado
  - [ ] X-Content-Type-Options configurado

---

## 📊 Monitoramento

- [ ] **Logs**
  - [ ] Logs de erro configurados
  - [ ] Logs não expõem dados sensíveis
  - [ ] Sistema de alertas configurado

- [ ] **Analytics** (opcional)
  - [ ] Google Analytics ou similar configurado
  - [ ] Eventos importantes rastreados
  - [ ] GDPR compliance verificado

- [ ] **Error Tracking**
  - [ ] Sentry ou similar configurado
  - [ ] Source maps carregados
  - [ ] Alertas de erro configurados

---

## 📝 Documentação

- [ ] **README**
  - [ ] Instruções de deploy atualizadas
  - [ ] URLs de staging/prod documentadas
  - [ ] Credenciais de teste documentadas (se aplicável)

- [ ] **CHANGELOG**
  - [ ] Versão atualizada
  - [ ] Mudanças documentadas
  - [ ] Data de release adicionada

- [ ] **API**
  - [ ] Endpoints documentados
  - [ ] Contratos de API atualizados
  - [ ] Exemplos de request/response atualizados

---

## 🚀 Deploy

### Build

- [ ] **Build de Produção**
  ```bash
  npm run build
  ```
  - [ ] Sem erros
  - [ ] Sem warnings críticos
  - [ ] Bundle size aceitável

- [ ] **Assets**
  - [ ] Imagens otimizadas
  - [ ] Fonts carregados
  - [ ] SVGs otimizados

### Upload

- [ ] **Arquivos**
  - [ ] Pasta `/dist` completa
  - [ ] `.htaccess` ou equivalente (se necessário)
  - [ ] Arquivos de configuração de servidor

- [ ] **CDN** (se aplicável)
  - [ ] Assets estáticos no CDN
  - [ ] Cache configurado
  - [ ] Invalidação de cache testada

### Configuração do Servidor

- [ ] **Web Server**
  - [ ] Configuração de SPA (redirect para index.html)
  - [ ] Gzip/Brotli ativo
  - [ ] Cache headers corretos

- [ ] **DNS**
  - [ ] Domínio aponta para servidor correto
  - [ ] Subdomínios configurados (www, etc.)
  - [ ] TTL apropriado

---

## ✅ Post-Deploy

### Verificação Imediata

- [ ] **Smoke Tests**
  - [ ] Site carrega sem erro 404/500
  - [ ] Login funciona
  - [ ] Navegação principal funciona
  - [ ] API conecta corretamente

- [ ] **Monitoramento**
  - [ ] Verificar logs por erros
  - [ ] Verificar métricas de performance
  - [ ] Verificar error tracking

### Comunicação

- [ ] **Stakeholders**
  - [ ] Product Owner notificado
  - [ ] Equipe de QA notificada
  - [ ] Documentação de release enviada

- [ ] **Usuários** (se aplicável)
  - [ ] Changelog comunicado
  - [ ] Downtime planejado comunicado
  - [ ] Novas features destacadas

### Backup

- [ ] **Rollback Plan**
  - [ ] Build anterior preservado
  - [ ] Processo de rollback documentado
  - [ ] Testado rollback (se possível)

---

## 🐛 Troubleshooting

### Problemas Comuns

**Site não carrega**
- Verificar configuração de servidor
- Verificar DNS
- Verificar certificado SSL
- Verificar console do browser

**Login não funciona**
- Verificar URL da API
- Verificar CORS
- Verificar cookies (SameSite, Secure)
- Verificar network tab

**Assets não carregam**
- Verificar base URL no build
- Verificar CDN
- Verificar cache
- Verificar CSP headers

**Performance ruim**
- Verificar size do bundle
- Verificar compressão
- Verificar cache
- Verificar CDN

---

## 📞 Contatos de Emergência

**Em caso de problemas críticos:**

- **DevOps**: [Nome/Email/Telefone]
- **Backend Lead**: [Nome/Email/Telefone]
- **Frontend Lead**: [Nome/Email/Telefone]
- **Product Owner**: [Nome/Email/Telefone]

**Ferramentas:**
- **Servidor**: [URL de admin]
- **Logs**: [URL de logs]
- **Monitoring**: [URL de monitoring]
- **Error Tracking**: [URL Sentry/etc]

---

## 📋 Checklist Resumido

**Antes do Deploy:**
- [ ] Testes manuais completos
- [ ] Build sem erros
- [ ] Variáveis de ambiente configuradas
- [ ] Backend funcionando

**Durante o Deploy:**
- [ ] Build de produção
- [ ] Upload de arquivos
- [ ] Configuração de servidor
- [ ] DNS atualizado

**Após o Deploy:**
- [ ] Smoke tests
- [ ] Monitoramento ativo
- [ ] Stakeholders notificados
- [ ] Rollback plan ready

---

**Última atualização**: Outubro 2025  
**Versão**: 1.0.0
