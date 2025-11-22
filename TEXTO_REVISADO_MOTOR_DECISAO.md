# 3.3 Motor de Decisão

O motor de decisão constitui o núcleo lógico do sistema desenvolvido neste trabalho, sendo responsável por transformar dados brutos de postura em informações clínicas acionáveis. Sua função central é avaliar continuamente os eventos recebidos, compará-los com parâmetros clínicos predefinidos e decidir sobre a necessidade de emissão, manutenção ou encerramento de alertas. Esse componente pode ser entendido como o "cérebro" do sistema, pois nele estão concentradas as regras que traduzem recomendações da literatura em lógica computacional.

O ponto de partida para a concepção do motor de decisão foi a análise de protocolos clínicos voltados à prevenção de úlceras por pressão. Diversas diretrizes, tanto nacionais quanto internacionais, enfatizam a importância do reposicionamento periódico de pacientes acamados, com variação dos tempos máximos de acordo com o grau de risco individual. Essa lógica clínica foi incorporada diretamente ao motor, que consulta parâmetros de permanência por postura e perfil de risco **definidos na configuração do sistema**. Tais parâmetros podem ser carregados de variáveis de ambiente ou assumem valores padrão (120 minutos para perfil baixo, 90 minutos para médio e 60 minutos para alto), proporcionando flexibilidade de ajuste sem necessidade de recompilação do código. Assim, cada evento de postura recebido não é analisado isoladamente, mas sim contextualizado em relação ao histórico do paciente e aos limites clínicos aplicáveis.

## 3.3.1 Arquitetura e Separação de Responsabilidades

Antes de descrever o funcionamento interno do motor de decisão, é importante esclarecer sua posição na arquitetura geral do sistema. O processamento de eventos de postura envolve três componentes distintos, cada um com responsabilidade bem definida:

1. **Módulo de Filtragem de Qualidade** (`quality/filtro.py`): Recebe eventos brutos dos dispositivos ESP32 e realiza validação de integridade, descarte de dados com baixa confiança (abaixo de 60% por padrão), eliminação de duplicatas e ordenação temporal com buffer de jitter (5 segundos). Apenas eventos que passam por todas essas verificações são encaminhados ao motor de decisão.

2. **Motor de Decisão** (`nucleo/decisor.py`): Recebe eventos já validados e filtrados, calcula tempo acumulado por postura, compara com janelas temporais configuradas e decide sobre abertura ou fechamento de alertas com base em mecanismos de cooldown e histerese. Retorna alertas como estruturas de dados (dicionários Python), sem persistir diretamente no banco.

3. **Motor de Alertas e Supressão** (`modulo_alerta/engine.py`): Recebe os alertas gerados pelo motor de decisão e aplica regras de supressão baseadas em agendas clínicas (cirurgias, fisioterapia, etc.), podendo descartar alertas completamente, reduzir suas janelas temporais ou mantê-los inalterados conforme o contexto clínico.

Essa separação de responsabilidades garante modularidade, facilita testes unitários e permite evolução independente de cada componente. O motor de decisão, portanto, opera sobre dados já consistentes, concentrando-se exclusivamente na lógica temporal e clínica de geração de alertas.

## 3.3.2 Processamento Incremental e Estado do Decisor

O motor de decisão implementa processamento incremental, mantendo estado entre eventos sucessivos por meio da classe `EstadoDecisor`. Esse estado contém:

- **Perfil de risco e identificação do paciente**: Determinam as janelas temporais aplicáveis
- **Parâmetros configurados**: Janela de tempo máximo por perfil, cooldown entre alertas (padrão 10 minutos) e histerese para confirmação de reposicionamento (padrão 5 minutos)
- **Postura atual e início da sequência**: Rastreamento da "run" (sequência contínua) da mesma postura
- **Alerta ativo**: Referência ao alerta aberto, se houver, com timestamp de início
- **Postura baseline**: Postura que causou abertura do alerta ativo
- **Estado de movimento**: Timestamp de início de mudança de postura, usado pelo mecanismo de histerese
- **Cooldown**: Timestamp até o qual novos alertas estão bloqueados após fechamento
- **Último timestamp processado**: Garantia de ordenação temporal

A cada novo evento recebido, o motor atualiza esse estado de forma determinística, produzindo zero, um ou dois alertas (abertura e/ou fechamento) conforme a situação clínica detectada.

## 3.3.3 Lógica de Cálculo de Tempo Acumulado

O motor verifica a postura registrada no evento e calcula o tempo acumulado nessa posição. Esse cálculo baseia-se no conceito de "run": uma sequência contínua de eventos na mesma postura. Quando o primeiro evento de uma nova postura é recebido, o motor marca o timestamp como `run_inicio`. Enquanto eventos subsequentes mantêm a mesma postura, esse timestamp permanece fixo, e o tempo acumulado é calculado como a diferença entre o timestamp do evento atual e o `run_inicio`.

Caso ocorra mudança de postura, o motor reinicia o contador: atualiza o `run_inicio` para o timestamp do novo evento e marca a nova postura como corrente. Essa lógica simples mas robusta permite rastreamento preciso do tempo de permanência em cada posição, independentemente da frequência de envio de eventos pelos dispositivos.

Por exemplo, se um paciente permanece em decúbito dorsal das 10:00 às 11:30, o `run_inicio` será 10:00. Quando o primeiro evento de decúbito lateral é recebido às 11:30, o tempo acumulado em dorsal será 90 minutos. Simultaneamente, o `run_inicio` é atualizado para 11:30, e a contagem recomeça para a nova postura.

## 3.3.4 Abertura de Alertas

Uma vez calculado o tempo acumulado, o motor verifica se a permanência na postura atual excedeu a janela temporal definida para o perfil de risco do paciente. A decisão de abrir um alerta envolve três condições simultâneas:

1. **Tempo excedido**: O tempo desde `run_inicio` deve ter ultrapassado a janela configurada (60, 90 ou 120 minutos conforme o perfil)
2. **Ausência de alerta ativo**: Não pode haver alerta já aberto para o paciente
3. **Fora do período de cooldown**: O tempo atual deve ser posterior ao `cooldown_ate`, evitando abertura excessiva de alertas em curto período

Quando essas condições são satisfeitas, o motor gera um novo alerta com status "aberto" contendo:

- **Identificação do paciente** (`paciente_id`)
- **Timestamp de início do alerta**: Calculado como o máximo entre o tempo de detecção (run_inicio + janela) e o fim do cooldown, garantindo que alertas não sejam retroativos
- **Tipo**: "imobilidade" (único tipo implementado)
- **Perfil de risco**: "baixo", "medio" ou "alto"
- **Janela temporal aplicada**: Valor em minutos usado como limiar
- **Status**: "aberto"

O alerta gerado é adicionado à lista de alertas emitidos pelo motor e também armazenado no estado como `alerta_atual`. Simultaneamente, a postura que causou o alerta é registrada como `baseline_postura`, servindo de referência para o mecanismo de histerese.

É importante notar que o motor **não persiste** os alertas diretamente no banco de dados. Ele retorna estruturas de dados que serão processadas pela camada de interface (`interface/dao.py`), responsável pela persistência. Essa separação mantém o motor independente de detalhes de armazenamento.

## 3.3.5 Mecanismo de Cooldown

O período de cooldown desempenha papel fundamental na prevenção de fadiga de alerta. Trata-se de um intervalo de tempo mínimo entre alertas do mesmo tipo, configurado por padrão em 10 minutos. Sem esse mecanismo, o sistema poderia abrir sucessivos alertas para uma mesma condição, sobrecarregando a equipe clínica com notificações redundantes.

O funcionamento do cooldown é direto: após o fechamento de um alerta, o motor marca um timestamp `cooldown_ate` calculado como o tempo de fechamento mais o intervalo de cooldown. Durante esse período, mesmo que o paciente permaneça imobilizado por tempo superior à janela configurada, nenhum novo alerta será aberto. Apenas após o término do cooldown, se o paciente ainda estiver na mesma postura, um novo alerta poderá ser gerado.

Esse mecanismo reflete boas práticas de sistemas de alertas clínicos, onde a repetição excessiva pode levar à dessensibilização da equipe ("alert fatigue"). Com o cooldown, garante-se que apenas um alerta relevante seja emitido para cada episódio contínuo de imobilidade prolongada, respeitando o tempo necessário para que a equipe execute o reposicionamento e registre a intervenção.

## 3.3.6 Mecanismo de Histerese

Outro mecanismo essencial é a histerese, utilizada para o encerramento de alertas. Quando ocorre mudança de postura em relação à `baseline_postura` (aquela que causou abertura do alerta), o sistema não encerra imediatamente o alerta ativo, mas aguarda um período mínimo para confirmar que a mudança foi efetiva. Essa medida previne que transições rápidas, instáveis ou acidentais sejam interpretadas como reposicionamentos válidos.

O funcionamento da histerese envolve o rastreamento de tempo de movimento:

1. Quando a postura atual difere da `baseline_postura` pela primeira vez, o motor marca `movimento_inicio` com o timestamp atual
2. Em eventos subsequentes, se a postura continua diferente, o tempo de movimento é incrementado
3. Se a postura retorna à `baseline_postura` antes de completar a histerese, o `movimento_inicio` é resetado para `None`, cancelando o movimento
4. Apenas quando o tempo de movimento atinge ou excede a histerese configurada (padrão 5 minutos), o alerta é efetivamente fechado

Por exemplo, se um paciente em alerta por imobilidade em decúbito dorsal é movido para decúbito lateral às 14:00, mas retorna a dorsal às 14:03, o movimento é considerado insuficiente e o alerta permanece aberto. Se, por outro lado, o paciente permanece em lateral por 5 minutos ou mais, o alerta é fechado, reconhecendo um reposicionamento válido.

Esse mecanismo confere maior realismo clínico ao sistema, pois reflete a prática de considerar apenas mudanças mantidas por certo tempo como intervenções eficazes. Movimentos transitórios durante cuidados de higiene, por exemplo, não são suficientes para prevenir úlceras por pressão e, portanto, não devem encerrar alertas.

Quando a histerese é satisfeita, o motor fecha o alerta adicionando:

- **Timestamp de fim**: Momento em que a histerese foi completada
- **Status**: Alterado de "aberto" para "fechado"
- **Duração**: Tempo total em minutos entre abertura e fechamento

Simultaneamente, o motor atualiza `cooldown_ate` e limpa os campos de estado relacionados ao alerta (`alerta_atual`, `baseline_postura`, `movimento_inicio`), preparando-se para processar futuros episódios.

## 3.3.7 Integração com Sistema de Agendas

Após a geração de alertas pelo motor de decisão, um processamento adicional é aplicado pelo motor de alertas (`modulo_alerta/engine.py`), que verifica se o timestamp de cada alerta coincide com períodos de agendas clínicas cadastradas para o paciente. O sistema de agendas permite que a equipe configure intervenções previstas (cirurgias, exames, fisioterapia, etc.) e defina como os alertas devem ser tratados durante esses períodos.

Três modos de supressão são suportados:

1. **Suprimir**: O alerta é completamente descartado, não sendo persistido nem notificado. Útil para períodos em que o monitoramento de imobilidade é clinicamente irrelevante (ex: durante cirurgia sob anestesia).

2. **Reduzir**: A janela temporal do alerta é diminuída em um valor configurado (mantendo mínimo de 5 minutos). Por exemplo, se um paciente de perfil alto (janela 60min) está em sessão de fisioterapia com configuração de redução de 20min, alertas só serão gerados após 40 minutos de imobilidade. Útil para situações onde algum monitoramento é desejável, mas com limiar relaxado.

3. **Monitorar**: O alerta é mantido inalterado. Representa o modo normal de operação.

O sistema de agendas adiciona contexto clínico ao processo decisório, evitando alertas inapropriados e reduzindo falsos positivos. Essa integração ocorre de forma transparente: o motor de decisão opera independentemente, e as regras de supressão são aplicadas como filtro posterior, preservando a modularidade da arquitetura.

## 3.3.8 Tipos de Alertas e Escopo Atual

Na implementação atual, o motor de decisão gera exclusivamente alertas do tipo **"imobilidade"**, relacionados à permanência prolongada em uma mesma postura além da janela temporal configurada. Esse foco reflete o objetivo central do sistema: prevenção de úlceras por pressão através do monitoramento de reposicionamento.

Embora a arquitetura do motor permita extensão para outros tipos de alertas, funcionalidades como detecção de padrões inadequados de rotação postural (ex: alternância repetitiva entre apenas duas posturas sem variação) ou geração de alertas sobre qualidade de dados (ex: excesso de leituras com baixa confiança) **não estão implementadas** nesta versão. A filtragem de qualidade descarta eventos inconsistentes, mas não gera alertas específicos sobre problemas de confiabilidade do monitoramento.

Essa delimitação de escopo foi deliberada, priorizando a implementação robusta e clinicamente validada de um único tipo de alerta antes da expansão para funcionalidades adicionais. Trabalhos futuros podem explorar a adição de novos tipos de alerta, mantendo a mesma estrutura de processamento incremental e mecanismos de cooldown/histerese.

## 3.3.9 Modos de Processamento

O motor de decisão suporta dois modos de operação:

1. **Processamento Incremental** (`processar_alertas_incremental`): Adequado para sistemas em tempo real (stream processing), recebe um evento por vez e atualiza o estado mantido em memória ou sistema de cache (Redis). Esse modo permite latência mínima entre a detecção de imobilidade e a notificação, sendo ideal para monitoramento contínuo.

2. **Processamento em Lote** (`processar_alertas_lote`): Adequado para análise retrospectiva ou reprocessamento de dados históricos (batch processing), recebe uma sequência completa de eventos ordenados temporalmente e processa toda a série de uma vez. Internamente, utiliza o processamento incremental iterado sobre cada evento, consolidando os alertas ao final.

Ambos os modos compartilham a mesma lógica central, garantindo consistência de resultados independentemente da forma de invocação. A escolha entre modos depende do contexto de uso: monitoramento em tempo real utiliza o modo incremental integrado ao recebimento de eventos via API REST ou WebSocket, enquanto geração de relatórios ou reprocessamento após mudanças de configuração utiliza o modo em lote sobre dados armazenados.

## 3.3.10 Considerações sobre Parametrização

Todos os parâmetros temporais do motor de decisão (janelas por perfil de risco, cooldown e histerese) são definidos no módulo de configuração (`configuracao.py`), que carrega valores de variáveis de ambiente ou aplica defaults seguros. Essa abordagem oferece:

- **Flexibilidade de deployment**: Ambientes de desenvolvimento, homologação e produção podem ter parâmetros distintos sem alteração de código
- **Facilidade de ajuste**: Valores podem ser refinados com base em feedback clínico sem recompilação
- **Auditabilidade**: Configuração centralizada simplifica documentação e rastreamento de mudanças

Embora os parâmetros não sejam armazenados em tabela de banco de dados na versão atual, essa evolução é considerada para versões futuras, permitindo ajustes dinâmicos via interface administrativa e mantendo histórico de mudanças parametrizadas. A migração para armazenamento em banco exigiria adaptação mínima no código do motor, graças à abstração proporcionada pela classe `EstadoDecisor` e função `_perfil_config`.

Os valores padrão adotados (60/90/120 minutos para janelas, 10 minutos para cooldown, 5 minutos para histerese) foram escolhidos com base em revisão de literatura sobre prevenção de úlceras por pressão e validados em cenários de teste com dados simulados. Ajustes podem ser necessários conforme o sistema é implantado em contextos clínicos reais e feedback da equipe de enfermagem é incorporado.

## 3.3.11 Garantias de Consistência

O motor de decisão implementa verificações rigorosas para garantir processamento correto:

- **Ordenação temporal**: Eventos devem ser recebidos em ordem cronológica crescente. Violações dessa invariante resultam em exceção, sinalizando problema na camada de filtragem ou persistência.

- **Presença de campos obrigatórios**: Eventos devem conter `timestamp` e `postura`. A ausência desses campos causa exceção antes de qualquer processamento.

- **Tipo de estado**: A função de processamento incremental valida que o estado fornecido é uma instância de `EstadoDecisor`, prevenindo erros de uso da API.

- **Consistência de estado interno**: O motor mantém invariantes sobre o estado (ex: se há `alerta_atual`, deve haver `baseline_postura` e `alerta_inicio`). Violações dessas invariantes indicam bugs e são detectadas por exceções com mensagens específicas.

Essas garantias permitem que o motor opere com confiança em ambientes de produção, facilitando depuração quando problemas ocorrem e assegurando que alertas gerados refletem fielmente a condição clínica monitorada.

---

## 3.3.12 Síntese

O motor de decisão representa a tradução de conhecimento clínico sobre prevenção de úlceras por pressão em lógica computacional robusta e testável. Por meio de mecanismos de acumulação temporal, cooldown e histerese, o motor equilibra sensibilidade (detectar imobilidade prolongada) com especificidade (evitar alarmes falsos), produzindo alertas clinicamente relevantes que auxiliam a equipe de enfermagem na gestão de reposicionamento de pacientes em risco.

A separação clara de responsabilidades entre filtragem de qualidade, decisão de alertas e supressão por agendas confere ao sistema modularidade e extensibilidade, permitindo evolução independente de cada componente conforme requisitos clínicos emergem ou tecnologias de monitoramento avançam.
