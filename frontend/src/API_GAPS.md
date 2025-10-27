# Gaps de API e Melhorias Sugeridas

Este documento lista os endpoints e funcionalidades que o frontend espera mas que podem não estar implementados no backend, além de sugestões de melhorias.

## 🔴 Gaps Críticos

### 1. Endpoint de Estatísticas do Dashboard

**Status**: Ausente (calculado no frontend)

**Endpoint Esperado**:
```http
GET /api/stats
```

**Response Esperado**:
```json
{
  "activeAlerts": 5,
  "overdueAlerts": 2,
  "eventsToday": 12,
  "totalPatients": 15,
  "completionRate": 85.5
}
```

**Impacto**: Sem este endpoint, o frontend precisa baixar todos os alertas e eventos para calcular estatísticas, desperdiçando banda.

**Workaround Atual**: Frontend calcula estatísticas localmente após buscar alertas.

---

### 2. Display Name do Usuário

**Status**: Parcialmente implementado

**Problema**: O endpoint `POST /api/auth/register` aceita `display_name`, mas `GET /api/auth/me` não retorna este campo.

**Response Atual**:
```json
{
  "username": "alice"
}
```

**Response Esperado**:
```json
{
  "username": "alice",
  "display_name": "Alice Oliveira",
  "role": "enfermeira"
}
```

**Impacto**: UI só pode mostrar username em vez do nome completo do usuário.

**Workaround Atual**: Mostrar apenas username.

---

## 🟡 Gaps Importantes

### 3. Filtros de Alertas

**Status**: Parcialmente implementado

**Endpoint Atual**:
```http
GET /api/frontend/alerts?horas=24
```

**Filtros Desejados**:
```http
GET /api/frontend/alerts?riskLevel=high&status=pending&room=201A&limit=20&offset=0
```

**Parâmetros Sugeridos**:
- `riskLevel`: `high`, `medium`, `low`
- `status`: `pending`, `acknowledged`, `completed`
- `room`: string
- `patientId`: string
- `limit`: number (paginação)
- `offset`: number (paginação)
- `sortBy`: `nextRepositioning`, `riskLevel`, `createdAt`
- `sortOrder`: `asc`, `desc`

**Impacto**: Frontend precisa baixar todos os alertas e filtrar localmente.

**Workaround Atual**: Filtrar no frontend após fetch.

---

### 4. Filtros de Timeline

**Status**: Ausente

**Endpoint Atual**:
```http
GET /api/timeline
```

**Endpoint Desejado**:
```http
GET /api/timeline?pacienteId=PAC-0001&tipo=alert_completed&startDate=2025-10-01&endDate=2025-10-31
```

**Parâmetros Sugeridos**:
- `pacienteId`: string
- `tipo`: `alert_open`, `alert_acknowledged`, `alert_completed`, `repositioning`
- `startDate`: ISO 8601
- `endDate`: ISO 8601
- `limit`: number
- `offset`: number

**Impacto**: Frontend baixa todo o histórico, mesmo quando usuário quer ver apenas um paciente.

**Workaround Atual**: Filtrar e agrupar no frontend.

---

### 5. Busca de Pacientes

**Status**: Ausente

**Endpoint Desejado**:
```http
GET /api/pacientes/search?q=Maria&room=201
```

**Parâmetros Sugeridos**:
- `q`: busca por nome (string)
- `room`: filtro por quarto
- `riskLevel`: filtro por nível de risco

**Impacto**: UI não pode implementar busca eficiente.

**Workaround Atual**: Não implementado.

---

## 🟢 Melhorias Sugeridas

### 6. WebSocket para Alertas em Tempo Real

**Status**: Ausente

**Proposta**: Implementar WebSocket para notificações push de novos alertas.

**Endpoint Sugerido**:
```
ws://api.example.com/ws/alerts
```

**Mensagens**:
```json
{
  "type": "alert_created",
  "data": { /* Alert object */ }
}

{
  "type": "alert_acknowledged",
  "data": { "alertId": "..." }
}

{
  "type": "alert_completed",
  "data": { "alertId": "..." }
}
```

**Benefício**: Elimina necessidade de polling, reduz latência, economiza recursos.

**Workaround Atual**: Polling a cada 30 segundos.

---

### 7. Batch Operations

**Status**: Ausente

**Proposta**: Reconhecer/completar múltiplos alertas de uma vez.

**Endpoints Sugeridos**:
```http
POST /api/frontend/alerts/batch/acknowledge
Body: { "alertIds": ["id1", "id2", "id3"] }

POST /api/frontend/alerts/batch/complete
Body: { "alertIds": ["id1", "id2", "id3"] }
```

**Benefício**: Operações em lote mais eficientes para equipes de cuidado.

**Workaround Atual**: Loop de requisições individuais.

---

### 8. Upload de Documentos de Pacientes

**Status**: Ausente

**Proposta**: Permitir upload de documentos/imagens relacionados ao paciente.

**Endpoints Sugeridos**:
```http
POST /api/pacientes/{id}/documents
Content-Type: multipart/form-data

GET /api/pacientes/{id}/documents

DELETE /api/pacientes/{id}/documents/{docId}
```

**Benefício**: Anexar prontuários, imagens, PDFs ao registro do paciente.

**Workaround Atual**: Não implementado.

---

### 9. Relatórios e Exportação

**Status**: Ausente

**Proposta**: Gerar relatórios em PDF/CSV.

**Endpoints Sugeridos**:
```http
GET /api/reports/alerts?startDate=...&endDate=...&format=pdf
GET /api/reports/patients?format=csv
GET /api/reports/timeline?pacienteId=...&format=pdf
```

**Benefício**: Facilitar auditorias e análises.

**Workaround Atual**: Não implementado.

---

### 10. Notificações/Alertas para Usuários

**Status**: Ausente

**Proposta**: Sistema de notificações persistentes para usuários.

**Endpoints Sugeridos**:
```http
GET /api/notifications
POST /api/notifications/{id}/read
DELETE /api/notifications/{id}
```

**Response**:
```json
{
  "id": 123,
  "type": "alert_overdue",
  "message": "Alerta atrasado para paciente Maria Silva",
  "read": false,
  "createdAt": "2025-10-25T15:00:00"
}
```

**Benefício**: Usuários não perdem alertas importantes.

**Workaround Atual**: Não implementado.

---

### 11. Audit Log

**Status**: Ausente

**Proposta**: Log de auditoria de todas as ações.

**Endpoint Sugerido**:
```http
GET /api/audit?userId=...&action=...&startDate=...&endDate=...
```

**Response**:
```json
{
  "id": 1,
  "userId": "alice",
  "action": "alert_completed",
  "resourceId": "PAC-0001__...",
  "timestamp": "2025-10-25T15:30:00",
  "ipAddress": "192.168.1.100"
}
```

**Benefício**: Rastreabilidade completa para compliance e segurança.

**Workaround Atual**: Parcialmente coberto por timeline.

---

### 12. Configurações de Usuário

**Status**: Ausente

**Proposta**: Permitir que usuários configurem preferências.

**Endpoints Sugeridos**:
```http
GET /api/user/settings
PATCH /api/user/settings
```

**Settings Exemplo**:
```json
{
  "emailNotifications": true,
  "pollingInterval": 30,
  "theme": "light",
  "language": "pt-BR",
  "defaultView": "dashboard"
}
```

**Benefício**: Experiência personalizada por usuário.

**Workaround Atual**: Configurações apenas no localStorage (não persiste).

---

### 13. Permissões e Roles

**Status**: Parcialmente implementado

**Problema**: Não há sistema de permissões. Todos os usuários têm acesso total.

**Proposta**: Implementar roles e permissions.

**Roles Sugeridos**:
- `admin`: Acesso total
- `enfermeira`: Dashboard, alertas, pacientes, timeline
- `cuidador`: Dashboard, alertas (somente leitura em pacientes)
- `visualizador`: Somente leitura

**Endpoint Sugerido**:
```http
GET /api/auth/permissions
```

**Response**:
```json
{
  "role": "enfermeira",
  "permissions": [
    "alerts:read",
    "alerts:acknowledge",
    "alerts:complete",
    "patients:read",
    "patients:write",
    "timeline:read"
  ]
}
```

**Benefício**: Controle de acesso apropriado.

**Workaround Atual**: Todos têm acesso total.

---

## 📊 Priorização Sugerida

### Alta Prioridade
1. ✅ Display name no `/api/auth/me`
2. ✅ Endpoint `/api/stats` para dashboard
3. ✅ Filtros de alertas (riskLevel, status, room)

### Média Prioridade
4. ⚠️ WebSocket para real-time (substitui polling)
5. ⚠️ Filtros de timeline
6. ⚠️ Permissões e roles

### Baixa Prioridade
7. 📋 Batch operations
8. 📋 Upload de documentos
9. 📋 Relatórios e exportação
10. 📋 Notificações persistentes
11. 📋 Audit log
12. 📋 Configurações de usuário

---

## 🔧 Adaptações do Frontend

O frontend foi desenvolvido com flexibilidade para adaptar-se aos endpoints disponíveis:

### Se endpoint não existe:
- **Stats**: Calcula localmente
- **Filtros**: Filtra no frontend
- **WebSocket**: Usa polling como fallback
- **Batch**: Loop de requisições

### Quando endpoint for implementado:
- Substituir lógica do frontend
- Remover cálculos locais
- Melhorar performance

---

## 📝 Notas de Implementação

### Para o Backend Team:

1. **Manter compatibilidade**: Ao adicionar novos campos, garantir que campos antigos continuem funcionando.

2. **Versioning**: Considerar versionar a API (`/api/v1/...`) para mudanças breaking.

3. **Paginação**: Usar padrão consistente:
   ```json
   {
     "data": [...],
     "pagination": {
       "total": 100,
       "limit": 20,
       "offset": 0,
       "hasMore": true
     }
   }
   ```

4. **Error handling**: Retornar erros estruturados:
   ```json
   {
     "error": "Validation failed",
     "message": "Invalid patient data",
     "details": {
       "name": "Name is required",
       "room": "Room must be alphanumeric"
     }
   }
   ```

5. **Rate limiting**: Implementar rate limiting e retornar headers:
   ```
   X-RateLimit-Limit: 100
   X-RateLimit-Remaining: 95
   X-RateLimit-Reset: 1635724800
   ```

---

## 🤝 Feedback Loop

Este documento será atualizado conforme:
- Novos endpoints forem implementados
- Necessidades surgirem durante o uso
- Feedback dos usuários finais

**Última atualização**: Outubro 2025  
**Próxima revisão**: Após integração inicial com backend
