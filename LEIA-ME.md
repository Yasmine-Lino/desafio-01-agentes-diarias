# LEIA-ME — Instrução de Pedidos de Diárias

Projeto individual de **Yasmine Lino Franco** ([Yasmine-Lino](https://github.com/Yasmine-Lino)).

## Requisitos e instalação

O projeto foi desenvolvido e conferido no Windows com **Python 3.12.10**. Recomenda-se Python 3.12 para reproduzir o ambiente. As dependências estão fixadas em [requirements.txt](requirements.txt), incluindo Agno 3.2.1, Streamlit 1.67.0, OpenAI, Pydantic, python-dotenv e SQLAlchemy com suporte assíncrono.

As instruções para Linux e macOS são equivalentes, mas ainda não foram validadas nesses sistemas. Execute os comandos a partir da raiz do projeto.

### Windows — PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Testes offline:

```powershell
.\.venv\Scripts\python.exe -B -X utf8 testes\testar_ferramentas.py
.\.venv\Scripts\python.exe -B -X utf8 testes\testar_experimento_memoria_complementacoes_offline.py
.\.venv\Scripts\python.exe -B -X utf8 testes\testar_transporte_experimento_offline.py
.\.venv\Scripts\python.exe -B -X utf8 testes\auditar_evidencias_historicas.py
```

### Linux — terminal Bash

Instale Python 3.12, o módulo venv e o pip pelos meios apropriados à sua distribuição. Depois, na raiz do projeto:

```bash
python3.12 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

Testes offline:

```bash
./.venv/bin/python -B -X utf8 testes/testar_ferramentas.py
./.venv/bin/python -B -X utf8 testes/testar_experimento_memoria_complementacoes_offline.py
./.venv/bin/python -B -X utf8 testes/testar_transporte_experimento_offline.py
./.venv/bin/python -B -X utf8 testes/auditar_evidencias_historicas.py
```

### macOS — terminal zsh ou Bash

Instale Python 3.12 e confirme que o comando `python3.12` está disponível. Na raiz do projeto:

```bash
python3.12 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

Testes offline:

```bash
./.venv/bin/python -B -X utf8 testes/testar_ferramentas.py
./.venv/bin/python -B -X utf8 testes/testar_experimento_memoria_complementacoes_offline.py
./.venv/bin/python -B -X utf8 testes/testar_transporte_experimento_offline.py
./.venv/bin/python -B -X utf8 testes/auditar_evidencias_historicas.py
```

## Configuração e execução com modelo real

Copie [.env.example](.env.example) para `.env` e configure localmente a variável `OPENAI_API_KEY`. Nunca publique `.env` ou credenciais. A execução real utiliza a API OpenAI, pode gerar custos e gravar resultados. Para preservar as evidências da entrega, utilize uma cópia de trabalho separada.

**Windows — PowerShell:**

```powershell
Copy-Item .env.example .env
# Edite .env localmente e informe sua chave.
.\.venv\Scripts\python.exe testes\executar_pedido.py DIA-2026-0102
```

**Linux e macOS:**

```bash
cp .env.example .env
# Edite .env localmente e informe sua chave.
./.venv/bin/python testes/executar_pedido.py DIA-2026-0102
```

A execução sem chave válida não deve ser considerada um teste real do modelo. Os testes offline verificam componentes isolados e não substituem a validação de ponta a ponta.
## Interface autenticada

A interface Streamlit exige autenticação OIDC e configuração privada de um provedor de identidade. O extra de autenticação deve ser instalado na mesma versão fixada do Streamlit.

**Windows — PowerShell:**

```powershell
.\.venv\Scripts\python.exe -m pip install "streamlit[auth]==1.67.0"
```

**Linux e macOS:**

```bash
./.venv/bin/python -m pip install "streamlit[auth]==1.67.0"
```

Configure um provedor de identidade real e seus segredos na configuração privada de autenticação do Streamlit, com URI de retorno compatível com a implantação. Forneça ao processo do Streamlit estas duas variáveis pelo servidor:

| Variável | Formato |
|---|---|
| `BARREIRA_HMAC_CHAVE_HEX` | Chave estável de 32 bytes em hexadecimal, 64 caracteres |
| `TITULARES_OIDC_JSON` | Lista JSON de vínculos verificados com `iss`, `sub`, `matricula` e `protocolos` |

**Iniciar no Windows — PowerShell:**

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

**Iniciar no Linux ou macOS:**

```bash
./.venv/bin/python -m streamlit run app.py
```

A inicialização não substitui a configuração do provedor OIDC. Sem autenticação e vínculos autorizados, as operações protegidas não estarão disponíveis. A integração com um provedor OIDC real ainda não foi validada.

A interface exige identidade autenticada com validade vigente e vínculo de titular autorizado, inclusive para consultar históricos. O formulário de execução exibe progresso e permite complementar a diligência. A instrução conferida apresenta recomendação, seis verificações com fundamentos, consultas auditadas, alertas, pendências e minuta editável. O conferente registra seu encaminhamento e justifica divergências. Uma falha encaminha o caso à análise manual com mensagem padrão. A exclusão tem área própria e confirmação explícita. A proteção foi testada offline com identidade simulada. A integração com um provedor OIDC real permanece pendente.

## Decisões técnicas

- **Paralelismo e teto.** A configuração padrão é sequencial, com limite de oito chamadas de ferramenta, escolhido como teto de projeto acima das quatro consultas esperadas, com margem para chamadas adicionais sem ciclos longos. O fluxo observado usa quatro consultas e cinco chamadas ao modelo. O teste de paralelismo em 0101 mediu tempos e tokens, mas não determinou esse teto e teve uma execução por modo.
- **Memória.** Quando habilitado, o histórico da sessão é limitado aos três últimos runs, com protocolo em `session_id` e matrícula validada em `user_id`. Três runs são um limite de projeto para manter contexto recente e conter crescimento de entrada, não um resultado medido como ótimo. Os experimentos A/B/C ativam, respectivamente, nenhuma memória conversacional persistente, histórico da sessão e histórico com atualização de memória pessoal. As complementações recuperam dados administrativos validados da sessão original.
- **Verificação independente.** As ferramentas consultam dados locais e computam valores em Python. O código confere status e estrutura da resposta, exige a trilha esperada, confronta argumentos com o pedido e revalida critérios e cálculos. A interface exibe somente argumentos permitidos de consultas aprovadas.
- **Retenção e exclusão.** A cópia de trabalho guarda sessões, runs, eventos administrativos e, quando habilitadas, memórias do titular. O código limita o contexto recuperado e não define expiração automática dos registros. O titular autenticado pode pedir exclusão lógica da cópia interativa. A rotina confere vínculo, bloqueia novas gravações do titular e verifica resíduos por matrícula e nome. Vínculos ambíguos são encaminhados à revisão manual. Registros oficiais, históricos de medição e revisões humanas têm gestão separada. A rotina não mede resíduos físicos em páginas SQLite, WAL ou backups.

## Estrutura e entrega

| Caminho | Função |
|---|---|
| [agente.py](agente.py), [modelos.py](modelos.py), [ferramentas.py](ferramentas.py) | Orquestração do agente, contrato Pydantic e consultas |
| [validacao_normativa.py](validacao_normativa.py), [barreira_validacao.py](barreira_validacao.py) | Evidência normativa determinística e barreira de publicação |
| [complementacoes.py](complementacoes.py), [persistencia_sessoes.py](persistencia_sessoes.py), [execucao_interativa.py](execucao_interativa.py) | Diligência, recuperação do contexto e execução auditada |
| [app.py](app.py), [exclusao_memoria.py](exclusao_memoria.py), [barreira_persistente.py](barreira_persistente.py) | Interface, exclusão lógica e bloqueio de recriação |
| [dados/](dados/), [testes/](testes/), [resultados/](resultados/) | Acervo hipotético, scripts de teste e medição, evidências |
| [desenho.md](desenho.md), [relatorio.md](relatorio.md) | Desenho do processo, métricas e conclusão |

O gabarito pertence à avaliação externa e fica fora das entradas do agente. Antes de publicar ou compactar, confira o conteúdo do pacote e exclua `.env`, segredos do Streamlit, ambientes virtuais, caches, backups e bancos de trabalho, incluindo WAL e SHM. Preserve as evidências revisadas e confirme com o professor a distribuição dos materiais originais. Consulte o [relatório técnico](relatorio.md) para os resultados e a divergência de 0106.
