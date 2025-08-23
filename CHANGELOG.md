# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato segue em parte o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/)  
e este projeto adota [Semantic Versioning](https://semver.org/lang/pt-BR/).

---

## [v0.1.0] - 2025-08-22

### Adicionado
- **Simulador de posturas (eventos)**  
  - Geração de posturas com transições válidas, dwell time, falhas e refeições.  
  - Saída em grade (`timestamp`, `postura`) para inspeção em série temporal.  
  - Exportação opcional de eventos brutos com a flag `--eventos`.  

- **Testes automatizados**  
  - Teste básico de geração de sessão.  
  - Teste de reprodutibilidade (seed fixa).  
  - Teste de contagem de linhas.  

- **Integração Contínua (CI)**  
  - Configuração de GitHub Actions para rodar `pytest` em cada PR e push.  

---

[v0.1.0]: https://github.com/yaguts1/tcc2-agente-inteligente/releases/tag/v0.1.0