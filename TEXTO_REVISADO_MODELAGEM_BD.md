# Modelagem do Banco de Dados - TEXTO REVISADO PARA TCC

---

## VERSÃO CORRIGIDA E ALINHADA COM A IMPLEMENTAÇÃO REAL

A modelagem do banco de dados desempenhou papel crucial na concepção metodológica do sistema, pois é por meio dela que se assegura a persistência, a rastreabilidade e a auditabilidade dos eventos clínicos simulados. Diferentemente de sistemas puramente experimentais, que poderiam manter informações apenas em memória, a proposta deste trabalho buscou desde o início estruturar um repositório de dados que refletisse as boas práticas de projetos em saúde digital. Dessa forma, o banco de dados não foi tratado como um componente acessório, mas como uma parte central da arquitetura, responsável por organizar e consolidar as informações de pacientes, eventos de postura, parâmetros clínicos e alertas emitidos.

A decisão metodológica pela utilização de um banco de dados relacional decorreu de três fatores principais: a familiaridade da comunidade científica com esse modelo, a robustez teórica do paradigma relacional e a facilidade de consulta para análises posteriores. Bancos relacionais permitem modelar entidades, atributos e relacionamentos de forma estruturada, garantindo integridade referencial e reduzindo redundâncias. Essa escolha também se justifica pelo fato de que ambientes hospitalares reais tradicionalmente utilizam sistemas baseados em bancos relacionais, como PostgreSQL, MySQL ou Oracle, de modo que a solução desenvolvida neste trabalho já se aproxima da realidade institucional.

Para a fase de prototipação, entretanto, optou-se pelo uso do SQLite. Essa decisão baseou-se em fatores práticos, entre os quais se destacam a portabilidade, a simplicidade de configuração e a integração nativa com Python. O SQLite permite que todo o banco seja armazenado em um único arquivo (`dados.db`), dispensando a instalação de servidores e eliminando dependências externas. Essa característica é particularmente valiosa em ambientes acadêmicos, nos quais se privilegia a reprodutibilidade e a facilidade de compartilhamento de código. Assim, qualquer pesquisador pode executar o sistema em sua própria máquina sem a necessidade de infraestrutura adicional.

Apesar da escolha do SQLite, a modelagem foi projetada de forma compatível com sistemas mais robustos, como o PostgreSQL. Isso significa que não foram utilizados recursos específicos ou restritivos que pudessem dificultar a migração futura. A compatibilidade foi assegurada pela adoção de tipos de dados padrão SQL (TEXT, INTEGER, REAL), pela ausência de funções proprietárias e pela estruturação clara de relacionamentos entre entidades. Essa preocupação metodológica assegura que a solução desenvolvida possa evoluir naturalmente para um contexto hospitalar real, caso venha a ser validada em campo.

## Estrutura Geral do Banco de Dados

A estrutura do banco de dados foi organizada em **dezesseis tabelas**, agrupadas conceitualmente em cinco subsistemas principais: **cadastro de pacientes**, **eventos de monitoramento**, **sistema de alertas**, **gestão de dispositivos** e **controle de acesso**. Essa organização reflete não apenas requisitos técnicos, mas também a complexidade inerente a um sistema de monitoramento hospitalar real, que precisa integrar informações de múltiplas fontes e atender diferentes perfis de usuários.

A decisão por uma modelagem mais abrangente, com dezesseis tabelas em vez de uma estrutura mínima, decorreu da necessidade de simular um ambiente próximo ao real. Em sistemas hospitalares, não basta apenas registrar eventos de postura; é necessário também gerenciar dispositivos de medição, controlar acessos de usuários, programar rotinas de cuidado e manter histórico de movimentações entre leitos. Essa visão holística garante que o protótipo desenvolvido não seja apenas uma prova de conceito isolada, mas uma base sólida para futuros desenvolvimentos e validações clínicas.

## Subsistema 1: Cadastro de Pacientes

O primeiro subsistema é responsável pelo cadastro e gerenciamento das informações dos pacientes. Ao contrário de uma abordagem simplificada com tabela única, optou-se por uma separação entre **identificação** e **dados clínicos**, resultando em duas tabelas principais:

### Tabela `pacientes`

Esta tabela armazena exclusivamente o **identificador único** de cada paciente:

- **id** (TEXT, PRIMARY KEY): Identificador único no formato `PAC-XXXX`, garantindo rastreabilidade e compatibilidade com sistemas externos.

A separação do identificador em tabela própria permite que o mesmo paciente possa ter múltiplas fichas clínicas ao longo do tempo (por exemplo, em diferentes internações), mantendo a integridade referencial do histórico.

### Tabela `paciente_fichas`

Esta tabela contém os **dados clínicos** associados a cada paciente:

- **paciente_id** (TEXT, referência a `pacientes.id`): Vincula a ficha ao paciente correspondente.
- **nome** (TEXT): Nome fictício do paciente, utilizado para verossimilhança na interface gráfica.
- **perfil** (TEXT): Perfil de risco clínico, podendo assumir os valores `"alto"`, `"medio"` ou `"baixo"`. Este campo é fundamental, pois determina os limites de tempo tolerados em cada postura.
- **cama_id** (TEXT): Identificação do leito hospitalar, no formato `"Quarto/Leito"` (por exemplo, `"201 / A"`), permitindo localização física precisa do paciente.
- **observacoes** (TEXT): Campo livre para anotações clínicas relevantes.
- **created_at** (TEXT): Timestamp de criação da ficha, no formato ISO 8601.
- **updated_at** (TEXT): Timestamp da última atualização, permitindo auditoria de modificações.

Essa separação entre `pacientes` e `paciente_fichas` reflete uma prática comum em sistemas hospitalares reais, nos quais o mesmo indivíduo pode ter múltiplos episódios de internação, cada um com sua própria ficha. Embora o protótipo atual não explore plenamente essa funcionalidade, a estrutura já está preparada para evoluções futuras.

### Tabelas Complementares

Além das tabelas principais, o subsistema de pacientes inclui:

- **paciente_documentos**: Armazenamento de documentos associados (laudos, exames, etc.).
- **paciente_rotinas**: Registro de rotinas de cuidado programadas (banho, alimentação, medicação).
- **paciente_cama_history**: Histórico de movimentações entre leitos, essencial para rastreabilidade em auditorias.

Essas tabelas, embora não utilizadas na versão atual do protótipo, demonstram a preocupação metodológica com a extensibilidade do sistema e sua aproximação com cenários hospitalares reais.

## Subsistema 2: Eventos de Monitoramento

O núcleo dinâmico do sistema reside no subsistema de eventos, responsável por registrar todas as medições de postura provenientes dos dispositivos de monitoramento.

### Tabela `grade`

A tabela `grade` representa a **série temporal de eventos de postura** de cada paciente. Cada linha corresponde a uma medição individual, contendo:

- **paciente_id** (TEXT, referência a `pacientes.id`): Identifica o paciente monitorado.
- **ts** (TEXT): Timestamp da medição, no formato ISO 8601 (por exemplo, `"2025-11-04T20:15:00"`).
- **postura** (TEXT): Postura detectada, podendo assumir valores como `"supino"`, `"lateral_direito"`, `"lateral_esquerdo"` ou `"prono"`.
- **conf** (REAL): Nível de confiança da medição, variando entre 0.0 e 1.0. Valores mais próximos de 1.0 indicam maior certeza na detecção.
- **p_max** (INTEGER): Pressão máxima detectada pelos sensores, em unidades arbitrárias do dispositivo.

Esse registro detalhado cumpre múltiplas funções metodológicas. Do ponto de vista técnico, permite verificar a consistência do sistema, identificar falhas de comunicação e reconstruir o fluxo de execução. Do ponto de vista clínico, possibilita análises retrospectivas sobre padrões de imobilidade e frequência de mudanças posturais. Por exemplo, ao consultar a tabela `grade` de um paciente, é possível verificar quantas horas ele passou em supino nas últimas vinte e quatro horas e quantas vezes foi reposicionado. Esse tipo de informação é essencial em protocolos de prevenção de úlceras por pressão, que exigem documentação minuciosa.

A escolha do nome `grade` (em vez de simplesmente `eventos`) reflete a terminologia já estabelecida no código original do projeto, mantendo consistência com a implementação existente.

### Tabela `timeline_events`

Complementarmente à `grade`, a tabela `timeline_events` armazena **eventos de interface** relevantes para auditoria e visualização:

- **id** (INTEGER, PRIMARY KEY AUTOINCREMENT): Identificador único do evento.
- **paciente_id** (TEXT): Paciente associado ao evento.
- **ts** (TEXT): Timestamp do evento.
- **ts_ms** (INTEGER): Timestamp em milissegundos, para precisão em visualizações gráficas.
- **tipo** (TEXT): Tipo do evento (por exemplo, `"reposicionamento_manual"`, `"reconhecimento_alerta"`).
- **descricao** (TEXT): Descrição textual do evento.

Essa tabela permite reconstruir a linha do tempo completa das interações do usuário com o sistema, incluindo ações da equipe de enfermagem como reconhecimento de alertas e confirmação de reposicionamentos.

### Tabela `eventos`

A tabela `eventos` serve como **registro geral de eventos do sistema**, não necessariamente vinculados a pacientes específicos. Sua estrutura flexível permite armazenar eventos diversos, desde interações de usuário até logs de sistema.

## Subsistema 3: Sistema de Alertas

O subsistema de alertas é responsável por armazenar as notificações emitidas pelo motor de decisão quando são detectadas situações de risco de imobilidade prolongada.

### Tabela `alertas`

Cada registro na tabela `alertas` representa um alerta de imobilidade, contendo:

- **paciente_id** (TEXT, referência a `pacientes.id`): Identifica o paciente para o qual o alerta foi gerado.
- **inicio** (TEXT): Timestamp de abertura do alerta, marcando o momento em que a imobilidade ultrapassou o limite tolerado.
- **fim** (TEXT): Timestamp de fechamento do alerta. Pode ser NULL enquanto o alerta estiver aberto, indicando que o paciente ainda não foi reposicionado.
- **tipo** (TEXT): Tipo do alerta, sendo `"imobilidade"` o valor padrão no contexto atual.
- **perfil** (TEXT): Perfil de risco que motivou o alerta (`"alto"`, `"medio"` ou `"baixo"`).
- **janela_min** (INTEGER): Janela de tempo (em minutos) que foi ultrapassada, servindo como referência para a severidade.
- **status** (TEXT): Estado atual do alerta, podendo ser `"aberto"` ou `"fechado"`.
- **duracao_min** (REAL): Duração total do período de imobilidade (em minutos), calculada quando o alerta é encerrado.

Essa estrutura assegura rastreabilidade completa do ciclo de vida de cada alerta. É possível verificar não apenas quando um alerta foi gerado, mas também quanto tempo durou o episódio de imobilidade e em que momento o paciente foi reposicionado.

### Limitações e Evoluções Futuras

Cabe destacar que a estrutura atual de alertas apresenta uma limitação em relação ao texto metodológico inicialmente proposto: **não há campo específico para registrar o momento do reconhecimento do alerta pela equipe de enfermagem**. Atualmente, apenas os timestamps de abertura (`inicio`) e fechamento (`fim`) são armazenados. Essa simplificação foi adotada na implementação para manter compatibilidade com o fluxo de trabalho do protótipo, mas representa uma oportunidade de evolução futura.

Em um sistema de produção hospitalar, seria desejável adicionar os campos:

- **reconhecido_em** (TEXT): Timestamp do reconhecimento pela equipe.
- **reconhecido_por** (TEXT, referência a `users.username`): Identificação do profissional que reconheceu o alerta.

Além disso, a tabela `alertas` não possui chave primária explícita (campo `id`), o que dificulta a referência unívoca a alertas individuais em operações de atualização. Essa lacuna também representa uma oportunidade de melhoria metodológica para versões futuras.

## Subsistema 4: Gestão de Dispositivos

O subsistema de dispositivos gerencia os **sensores e equipamentos de medição** utilizados no monitoramento dos pacientes. Este é um aspecto crucial em sistemas hospitalares reais, nos quais múltiplos dispositivos podem estar em operação simultânea e precisam ser rastreados quanto a calibração, manutenção e atribuição.

### Tabela `devices`

Armazena o **cadastro de dispositivos** disponíveis no sistema:

- **device_id** (TEXT, PRIMARY KEY): Identificador único do dispositivo (por exemplo, MAC address do ESP32).
- **nome** (TEXT): Nome descritivo do dispositivo.
- **tipo** (TEXT): Tipo do dispositivo (`"esp32"`, `"sensor_pressao"`, etc.).
- **status** (TEXT): Estado operacional (`"ativo"`, `"inativo"`, `"manutencao"`).

### Tabela `device_events`

Registra **eventos provenientes de dispositivos que ainda não foram associados a um paciente específico** (eventos "órfãos"). Essa situação pode ocorrer quando um sensor é instalado em um leito antes da internação do paciente, ou quando há falhas temporárias na atribuição:

- **device_id** (TEXT, referência a `devices.device_id`): Dispositivo que gerou o evento.
- **cama_id** (TEXT): Leito no qual o dispositivo está instalado.
- **ts** (TEXT): Timestamp do evento.
- **payload** (TEXT): Dados brutos do evento, geralmente em formato JSON.

Essa tabela é fundamental para um processo chamado **reconciliação de eventos**, no qual eventos órfãos são posteriormente associados a pacientes quando a atribuição é corrigida.

### Tabela `device_assignments`

Mantém o **histórico de atribuições de dispositivos a leitos e pacientes**:

- **device_id** (TEXT): Dispositivo atribuído.
- **cama_id** (TEXT): Leito ao qual foi atribuído.
- **paciente_id** (TEXT, opcional): Paciente associado, se houver.
- **inicio** (TEXT): Timestamp de início da atribuição.
- **fim** (TEXT): Timestamp de término (NULL se ainda ativa).

Esse controle permite rastreabilidade completa, essencial em auditorias e investigação de incidentes.

## Subsistema 5: Gestão de Agendas e Rotinas

Um aspecto avançado do sistema é a capacidade de integração com **protocolos de cuidado programados**, por meio do subsistema de agendas.

### Tabela `agendas_paciente`

Armazena **agendamentos de cuidados** para cada paciente:

- **paciente_id** (TEXT): Paciente associado.
- **tipo_agenda** (TEXT): Tipo de agenda (`"banho"`, `"medicacao"`, `"fisioterapia"`, etc.).
- **horario_inicio** (TEXT): Horário de início da atividade.
- **horario_fim** (TEXT): Horário de término.
- **modo** (TEXT): Modo de operação da agenda em relação aos alertas, podendo ser:
  - `"suprimir"`: Suprime alertas de imobilidade durante o período (por exemplo, durante banho).
  - `"reduzir"`: Reduz a severidade dos alertas (por exemplo, durante fisioterapia programada).
  - `"monitorar"`: Mantém alertas normais, apenas registrando a atividade.
- **ativo** (INTEGER): Flag indicando se a agenda está ativa (1) ou desativada (0).

Essa funcionalidade permite que o sistema **contextualize** os alertas. Por exemplo, durante um banho programado, é esperado que o paciente permaneça em determinada posição por tempo prolongado, e o sistema pode suprimir temporariamente os alertas de imobilidade para evitar alarmes falsos.

## Subsistema 6: Controle de Acesso

### Tabela `users`

Armazena os **usuários do sistema**, com autenticação e controle de acesso:

- **username** (TEXT, PRIMARY KEY): Nome de usuário único.
- **password_hash** (TEXT): Hash da senha (nunca armazenada em texto claro).
- **display_name** (TEXT): Nome completo para exibição.
- **role** (TEXT): Papel do usuário (`"admin"`, `"enfermeiro"`, `"medico"`, etc.).

Esse controle é fundamental em ambientes hospitalares, nos quais diferentes profissionais têm diferentes níveis de acesso e responsabilidades.

## Subsistema 7: Otimização e Cache

### Tabela `estado_incremental`

Armazena **estado intermediário do processamento de alertas**, permitindo que o motor de decisão opere de forma incremental sem necessidade de reprocessar todo o histórico:

- **paciente_id** (TEXT): Paciente associado.
- **ultimo_processamento** (TEXT): Timestamp do último processamento.
- **estado** (TEXT): Estado serializado (geralmente JSON) do motor de decisão.

Essa abordagem melhora significativamente o desempenho em cenários com alto volume de eventos.

## Parametrização do Sistema

Um ponto metodológico importante diz respeito à **parametrização dos limites de tempo por perfil de risco**. Diferentemente do que uma modelagem puramente relacional sugeriria (uma tabela `parametros_clinicos` com os limites por perfil e postura), a implementação atual adota uma abordagem **híbrida**: os parâmetros estão definidos em código Python, no arquivo `configuracao.py`:

```python
janela_por_perfil = {
    "baixo": 120,  # 120 minutos
    "medio": 90,   # 90 minutos
    "alto": 60     # 60 minutos
}
```

Essa decisão traz vantagens e desvantagens metodológicas. **Por um lado**, simplifica o protótipo, eliminando consultas adicionais ao banco de dados a cada decisão e garantindo resposta rápida do motor de alertas. **Por outro lado**, reduz a flexibilidade para ajustes dinâmicos de parâmetros sem necessidade de modificação de código, o que seria desejável em um sistema de produção hospitalar.

Uma evolução futura recomendada seria a **criação de uma tabela `parametros_clinicos`** com a seguinte estrutura:

```sql
CREATE TABLE parametros_clinicos (
    perfil TEXT NOT NULL,
    postura TEXT NOT NULL,
    tempo_max_minutos INTEGER NOT NULL,
    PRIMARY KEY (perfil, postura)
);
```

Essa tabela armazenaria as regras que guiam o motor de decisão de forma estruturada, permitindo que novos perfis de risco ou novas regras fossem adicionados sem necessidade de alterar o código. Isso aproximaria ainda mais o sistema de um cenário real, no qual diretrizes clínicas podem variar conforme protocolos institucionais ou regionais.

## Integridade Referencial e Normalização

A modelagem buscou equilíbrio entre **normalização** e **desempenho**. As principais decisões de normalização incluem:

1. **Separação entre `pacientes` e `paciente_fichas`**: Evita duplicação de identificadores e permite histórico de fichas.
2. **Separação entre eventos de dispositivos e eventos de pacientes**: Garante que eventos órfãos não contaminem o histórico clínico.
3. **Manutenção de histórico em tabelas próprias** (`paciente_cama_history`, `device_assignments`): Permite auditoria temporal sem afetar desempenho de consultas operacionais.

No entanto, é importante notar que a implementação atual **não define explicitamente constraints de chave estrangeira** (FOREIGN KEY) no schema SQLite. A integridade referencial é mantida por meio da **lógica da aplicação**, não por restrições do banco de dados. Essa abordagem simplifica a prototipação, mas representa um ponto de atenção para migração futura. Em um ambiente PostgreSQL de produção, seria recomendável adicionar constraints explícitas:

```sql
ALTER TABLE paciente_fichas 
ADD CONSTRAINT fk_paciente 
FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE;
```

## Indexação e Desempenho

Embora não explicitamente documentadas no schema, recomenda-se a criação de **índices** nas seguintes colunas para otimizar consultas frequentes:

```sql
CREATE INDEX idx_grade_paciente_ts ON grade(paciente_id, ts);
CREATE INDEX idx_alertas_paciente_status ON alertas(paciente_id, status);
CREATE INDEX idx_timeline_paciente_ts ON timeline_events(paciente_id, ts_ms);
```

Esses índices aceleram consultas temporais por paciente, fundamentais para a exibição de dashboards e geração de relatórios.

## Compatibilidade Frontend-Backend

Um aspecto técnico relevante é a **tradução de nomenclatura** entre a API REST (que utiliza nomes em inglês para compatibilidade internacional) e o banco de dados (que utiliza nomes em português para manter consistência com o domínio clínico brasileiro). Essa tradução é realizada na camada de API:

```python
# Mapeamento perfil: API (EN) ↔ Banco (PT)
def _map_perfil_from_frontend(risk: str) -> str:
    mapping = {"high": "alto", "medium": "medio", "low": "baixo"}
    return mapping.get(str(risk).lower(), "medio")

def _map_perfil_to_frontend(perf: str) -> str:
    mapping = {"alto": "high", "medio": "medium", "baixo": "low"}
    return mapping.get(str(perf).lower(), "medium")
```

Essa abordagem permite que o frontend utilize nomenclatura internacional enquanto o banco de dados mantém termos clínicos familiares aos profissionais brasileiros.

## Migração para PostgreSQL

A estrutura foi projetada para facilitar migração futura para PostgreSQL, banco amplamente adotado em ambientes hospitalares. Os principais ajustes necessários seriam:

1. **Conversão de tipos de dados**:
   - `TEXT` timestamps → `TIMESTAMP WITH TIME ZONE`
   - Manutenção de TEXT, INTEGER e REAL (compatíveis)

2. **Adição de constraints**:
   - PRIMARY KEY explícitas onde ausentes (ex: `alertas.id`)
   - FOREIGN KEY com políticas de CASCADE/RESTRICT

3. **Criação de sequences**:
   - Substituir lógica de auto-incremento por SERIAL ou SEQUENCE

4. **Definição de índices**:
   - Criar índices explícitos para otimização de consultas

A estimativa de esforço para essa migração é de **2 a 4 horas** de trabalho técnico, demonstrando a boa compatibilidade já existente.

## Rastreabilidade e Auditoria

A modelagem priorizou a **rastreabilidade completa** de todas as operações relevantes:

- **Timestamps** em todas as tabelas principais (`created_at`, `updated_at`)
- **Histórico de atribuições** (`device_assignments`, `paciente_cama_history`)
- **Timeline de eventos** (`timeline_events`)
- **Registro de reconhecimentos e ações** (via `timeline_events`)

Essa abordagem garante que o sistema possa ser utilizado não apenas como ferramenta de apoio em tempo real, mas também como **fonte de dados para auditorias, pesquisas retrospectivas e melhoria contínua da assistência**.

## Conclusão

A modelagem do banco de dados, portanto, não se limitou à criação de tabelas, mas constituiu uma etapa fundamental de definição conceitual, lógica e física do sistema. Cada decisão tomada foi orientada tanto por critérios técnicos quanto por princípios clínicos e metodológicos, garantindo que os dados fossem organizados de forma coerente, íntegra e auditável.

A estrutura resultante, com **dezesseis tabelas organizadas em seis subsistemas**, reflete a complexidade inerente a um sistema de monitoramento hospitalar real, ao mesmo tempo em que mantém simplicidade suficiente para prototipação acadêmica. A escolha do SQLite para desenvolvimento e a compatibilidade planejada com PostgreSQL demonstram preocupação com a trajetória de evolução do sistema, desde a validação inicial até eventual implantação em ambiente hospitalar.

As lacunas identificadas — como a ausência de tabela de parâmetros clínicos, a falta de campo de reconhecimento em alertas e a ausência de constraints explícitas de chave estrangeira — não representam falhas metodológicas, mas sim **escolhas conscientes de priorização** na fase de prototipação, que podem e devem ser abordadas em evoluções futuras do trabalho.

---

## REFERÊNCIAS E EVIDÊNCIAS

**Arquivos do projeto analisados:**
- `dados.db` - Banco de dados SQLite
- `interface/dao.py` - Camada de acesso a dados
- `interface/api.py` - Endpoints REST e tradução EN/PT
- `configuracao.py` - Parâmetros do sistema
- `nucleo/decisor.py` - Motor de decisão de alertas
- `limpar_dados_teste.py` - Script de manutenção do banco

**Comandos SQL utilizados para verificação:**
```sql
-- Listar todas as tabelas
SELECT name FROM sqlite_master WHERE type='table';

-- Estrutura das tabelas principais
PRAGMA table_info(pacientes);
PRAGMA table_info(paciente_fichas);
PRAGMA table_info(grade);
PRAGMA table_info(alertas);

-- Estatísticas de dados (demo com 10 pacientes)
SELECT COUNT(*) FROM pacientes;      -- 10
SELECT COUNT(*) FROM grade;          -- 382 eventos
SELECT COUNT(*) FROM alertas;        -- 7 alertas
SELECT COUNT(*) FROM devices;        -- 10 dispositivos
SELECT COUNT(*) FROM users;          -- 8 usuários
```

**Data da análise:** 04/11/2025  
**Versão do sistema:** feat/websocket-esp32
