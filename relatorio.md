# Relatório técnico final — Desafio 01

Projeto individual de **Yasmine Lino Franco** ([Yasmine-Lino](https://github.com/Yasmine-Lino)).

**Projeto:** Instrução de pedidos de diárias com agentes de IA
**Framework:** Agno
**Modelo utilizado:** gpt-5.6-luna
**Ambiente:** Python no Windows, com PowerShell
**Natureza:** Experimento acadêmico com dados e norma hipotéticos

## 1. Resumo executivo

Foi desenvolvido um agente de IA para apoiar a instrucao
de pedidos de diarias, mediante consulta a ferramentas
Python, aplicacao de regras normativas, producao de
saida estruturada e validacao independente.

O agente nao autoriza despesas e nao substitui a
conferencia humana nem a decisao do ordenador.

Na terceira rodada, foram obtidos 13 acertos integrais
em 14 pedidos (92,86%),
com 68 de 70 campos corretos
(97,14%).

A barreira independente aprovou tecnicamente as 14
instrucoes da terceira rodada. A concordancia com o
gabarito e a aprovacao tecnica sao indicadores distintos.

## 2. Objetivo e escopo

Automatizar parcialmente a conferencia preliminar de
pedidos de diarias, verificando cadastro, historico,
calculos, saldo orcamentario e requisitos normativos.

A solucao produz uma instrucao fundamentada e uma
recomendacao administrativa sujeita a revisao humana.

O conjunto de dados e as regras utilizados representam
um cenario hipotetico de aprendizagem, nao uma
autorizacao administrativa real.

## 3. Arquitetura e regras

Um agente Agno 3.2.1 usa `gpt-5.6-luna`, raciocínio configurado como `none`, telemetria desligada e limite de oito chamadas de ferramenta. O fluxo padrão é sequencial. A aplicação ancora matrícula e datas no pedido validado e invoca quatro ferramentas auditadas. [Agente](agente.py) · [Ferramentas](ferramentas.py)

| Ferramenta do agente | Função Python | Evidência produzida |
|---|---|---|
| `verificar_cadastro` | `consultar_servidor` | Correspondência do cadastro, grupo e lotação, com dados minimizados |
| `verificar_prestacoes` | `consultar_historico` | Diárias concedidas no mês e prestações vencidas |
| `verificar_calculo` | `calcular_diarias` | Antecedência, quantidade e valor pela tabela de grupo e destino |
| `verificar_orcamento` | `consultar_saldo` | Comparação do valor calculado com a dotação da unidade |

A norma hipotética exige dez dias corridos de antecedência. Urgência aceita pela norma requer autorização superior escrita. O cálculo usa uma diária por pernoite mais meia no retorno, ou meia diária sem pernoite. O limite é de dez diárias por mês civil, a prestação vence em cinco dias úteis após o retorno e o saldo deve ser suficiente. Dados incompletos ou divergentes geram diligência sem análise de mérito. [Norma do exercício](dados/normas.md)

O esquema Pydantic `Instrucao` contém protocolo, matrícula, quantidade e valor opcionais, recomendação, exigência de autorização superior, pendências, alertas e minuta. As seis instâncias de `Verificacao` documentam cadastro, dados completos, antecedência, prestação de contas, limite mensal e saldo orçamentário, cada qual com situação e fundamento. Campos extras, critérios repetidos e valores negativos ou não finitos são recusados. Status de execução, integridade da trilha, argumentos, cálculos e regra normativa são conferidos antes da publicação. [Modelos](modelos.py) · [Barreira normativa](barreira_validacao.py)

## 4. Processo de instrução

1. Receber e identificar o pedido.
2. Conferir campos e eventuais complementacoes.
3. Aplicar controles de dados pessoais.
4. Executar as ferramentas de verificacao.
5. Produzir instrucao estruturada com Pydantic.
6. Auditar chamadas e resultados das ferramentas.
7. Executar a barreira normativa independente.
8. Encaminhar a recomendacao para revisao humana.
9. Registrar a decisao humana quando aplicavel.

Pedidos incompletos podem exigir diligencia preliminar,
sem acionamento desnecessario do modelo.

## 5. Metodologia de avaliação

As três rodadas avaliaram 14 casos, correspondentes a 12 pedidos originais e duas complementações. A comparação usa os relatórios históricos da avaliação externa. O gabarito fica fora do fluxo do agente.

A avaliacao contra o gabarito considerou acertos
integrais por pedido e correspondencia de campos.

Separadamente, a barreira independente verificou
a consistencia tecnica e normativa das instrucoes.

As rodadas foram preservadas para permitir comparacao,
sem substituir resultados anteriores.

## 6. Resultados das três rodadas

| Indicador | Inicial | Rodada 2 | Rodada 3 |
|---|---:|---:|---:|
| Casos corretos | 8/14 | 13/14 | 13/14 |
| Acurácia por caso | 57,14% | 92,86% | 92,86% |
| Campos corretos | 61/70 | 68/70 | 68/70 |
| Acurácia por campo | 87,14% | 97,14% | 97,14% |

A terceira rodada manteve os indicadores da segunda.
A barreira tecnica aprovou 14/14 instrucoes na
terceira rodada, resultado distinto da concordancia
de 13/14 com o gabarito.

As fontes são a [rodada inicial](resultados/avaliacao_gabarito_rodada_inicial.json), a [rodada 2 final](resultados/avaliacao_gabarito_rodada2_final.json) e a [rodada 3](resultados/avaliacao_gabarito_rodada3.json). A [versão intermediária da rodada 2](resultados/avaliacao_gabarito_rodada2_consolidada.json) registra 12/14 casos e 67/70 campos. Os JSONs de [execuções históricas](resultados/execucoes/) trazem tempos e tokens quando disponíveis. A cobertura desses campos varia entre os registros, o que impede um total financeiro comparável das três rodadas.

| Rodada | Soma das durações registradas | Casos com duração | Soma dos tokens totais registrados | Casos com tokens |
|---|---:|---:|---:|---:|
| Inicial | 138,7647 s | 12/14 | 89.423 | 9/14 |
| 2 final | 132,4498 s | 12/14 | 95.121 | 9/14 |
| 3 | 113,9495 s | 11/14 | 138.090 | 11/14 |

Cada soma usa apenas os valores numéricos nos arquivos apontados pela avaliação correspondente. As somas de duração representam tempos por caso, sem medir a duração de parede de toda a rodada.

## 7. Divergência normativa - DIA-2026-0106

O pedido envolve situacao emergencial de combate
a incendio florestal.

O agente recomendou diligencia porque nao identificou
comprovacao estruturada da autorizacao superior escrita.

O gabarito esperava recomendacao favoravel, com
exigencia de autorizacao superior.

Os dois campos divergentes foram recomendacao e
criterios_nao_atendidos.

A divergencia foi preservada, sem inventar documento,
alterar o gabarito ou forcar correspondencia artificial.

O detalhamento encontra-se em:
`resultados/ANALISE_DIVERGENCIA_0106.md`.

## Memória e complementações

A diligência de 0111 registrou a ausência da data de retorno. A de 0112 registrou divergência cadastral, sem atribuir a sessão à matrícula incompatível. As correções foram validadas e recuperadas pelo protocolo da sessão original. O modelo recebeu dados corrigidos e resumo administrativo mínimo. A evidência separa esse contexto da conversa anterior e da memória pessoal.

| Rodada de memória | Evidência real |
|---|---|
| [8.10 inicial](resultados/experimentos_memoria_0111_0112/RELATORIO.md) | 0111/A iniciou com diligência local. A tentativa de retomada ficou sem resposta HTTP. As outras cinco combinações ficaram sem execução. |
| [8.10-D](resultados/experimentos_memoria_0111_0112_retomada_8_10_D/RELATORIO.md) | As seis combinações foram iniciadas. A e C passaram nos dois pedidos. B teve respostas HTTP 200 parciais nos dois pedidos e parou na preparação da chamada seguinte, antes da barreira. |
| [8.10-F](resultados/experimentos_memoria_0111_0112_validacao_B_8_10_F/RELATORIO.md) | Apenas 0111/B e 0112/B foram executados, com validação normativa em ambos. |

Nas execuções consolidadas, cada diligência foi local e teve zero chamadas. A análise de mérito ocorreu na retomada. A usou apenas persistência administrativa e B acrescentou histórico de até três runs. C acrescentou atualização de memória pessoal. Cada combinação usou SQLite descartável independente.

| Pedido | Modo | Tempo da retomada (s) | Chamadas análise / memória | Tokens entrada / saída / total | USD estimado |
|---|---|---:|---:|---:|---:|
| 0111 | A | 9,974 | 5 / 0 | 11.453 / 579 / 12.032 | 0,00151835 |
| 0111 | B | 9,483 | 5 / 0 | 11.453 / 537 / 11.990 | 0,00087616 |
| 0111 | C | 7,939 | 5 / 1 | 12.705 / 580 / 13.285 | 0,00180848 |
| 0112 | A | 8,432 | 5 / 0 | 11.260 / 554 / 11.814 | 0,00104220 |
| 0112 | B | 8,730 | 5 / 0 | 11.260 / 586 / 11.846 | 0,00093110 |
| 0112 | C | 8,243 | 5 / 1 | 12.523 / 578 / 13.101 | 0,00135670 |

As seis retomadas da tabela retornaram `apto_para_autorizacao` e passaram pela barreira. A diligência local não gerou conversa anterior. B e C persistiram o run da retomada, sem replay conversacional. C fez uma chamada adicional por pedido e registrou zero memórias pessoais persistidas ou recuperadas. Os dados sustentam a recuperação da complementação administrativa. Diferenças de tempo, tokens e custo não demonstram ganho de memória.

Os tempos por turno, os status e as fontes individuais constam da [comparação final](resultados/experimentos_memoria_0111_0112_validacao_B_8_10_F/COMPARACAO_FINAL.md). Os custos da tabela são estimativas sobre tokens reportados pelo provedor, com distinção entre entrada comum, entrada em cache e saída. O faturamento não foi consultado. O [experimento histórico com 0101](resultados/experimentos_memoria/comparacoes/resumo_comparativo.json) permanece separado.

## 9. Experimento de paralelismo

O pedido DIA-2026-0101 foi executado uma vez com
parallel_tool_calls=False e uma vez com
parallel_tool_calls=True, mantendo o mesmo modelo
e a memoria desativada.

| Indicador | Sequencial | Paralelo |
|---|---:|---:|
| Tempo | 10,937 s | 6,622 s |
| Tokens de entrada | 10782 | 4202 |
| Tokens de saida | 617 | 525 |
| Tokens totais | 11399 | 4727 |
| Ferramentas | 4 | 4 |
| Barreira | Aprovada | Aprovada |

A reducao observada foi de 39,45% no tempo
e 58,53% no total de tokens.

Ambas as execucoes produziram recomendacao
apto_para_autorizacao, com 3,5 diarias e R$ 980,00.

Os registros start_time/end_time das ferramentas mostram
uma sobreposicao de 0,000207 s entre as duas primeiras
chamadas na execucao paralela; na sequencial nao houve
sobreposicao. Isso comprova paralelismo efetivo nesse par
e nessa execucao, mas nao simultaneidade das quatro
ferramentas. Houve uma execucao por modo, sem base para
generalizar a diferenca de desempenho.

## 10. Testes de falhas controladas

Foram simuladas quatro falhas, utilizando evidencias
validas e alteracoes somente em memoria:

| Cenario | Verificacoes | Resultado |
|---|---:|---|
| Erro em ferramenta obrigatoria | 4/4 | Bloqueado |
| Ferramenta obrigatoria ausente | 5/5 | Bloqueado |
| Valor financeiro adulterado | 6/6 | Bloqueado |
| Quantidade de diarias adulterada | 7/7 | Bloqueado |

Total: 22/22 verificacoes aprovadas.

Esses resultados demonstram a resposta da barreira
aos quatro cenarios simulados. Nao equivalem a testes
de indisponibilidade real de servicos externos.

Uma reprodução offline adicional, separada das
verificações históricas acima, está em
`resultados/evidencia_falhas_barreira_offline.txt`.
O comando `.venv\Scripts\python.exe -B -X utf8
testes\testar_falhas_barreira_offline.py` executa
quatro testes com dados e dependências normativas
sintéticos. Os casos cobrem erro em ferramenta
obrigatória, ferramenta ausente, valor financeiro
adulterado e quantidade adulterada. Os quatro foram
bloqueados pela barreira. Esta evidência representa
4 testes novos, não reproduz as 22 verificações
históricas nem altera os resultados anteriores.

## Segurança, revisão humana e exclusão

- As quatro consultas do acervo foram testadas diretamente, sem agente. Os casos 0112, 0108, 0103 e 0110 validaram, respectivamente, divergência cadastral, prestação vencida, meia diária e falta de saldo. [Evidência offline](resultados/evidencia_offline_ferramentas_8_9.txt)
- A justificativa é tratada como dado não confiável. Os filtros de CPF, e-mail e dados bancários preservam os identificadores operacionais. No cenário offline de 0104, a inspeção usa mensagens efetivamente entregues ao modelo simulado e conteúdo lógico do SQLite temporário. As suítes de contexto e Streamlit também verificam complementações, consultas auditadas e recusa de resultados incompatíveis. [Segurança](testes/testar_seguranca.py) · [Contexto](testes/testar_contexto_complementacoes_offline.py) · [Streamlit](testes/testar_streamlit_offline.py)
- O conferente vê a instrução aprovada, fundamentos, alertas, pendências e consultas com uma lista permitida de argumentos. Pode editar a minuta e registrar o encaminhamento com justificativa de divergência. O fluxo envia falhas ou resultados recusados para análise manual. A conferência fica entre a validação automática e a decisão do ordenador, porque uma divergência pode atravessar a cadeia e aparecer apenas na auditoria.
- Na área separada de exclusão, o titular autenticado confirma a solicitação. A rotina limita o alcance à cópia de trabalho. Confere a titularidade, exclui sessões e suas execuções vinculadas e usa `delete_user_memories` para as memórias. A auditoria de resíduos busca matrícula e nome, inclusive em JSON. Vínculos ambíguos exigem revisão manual. Um bloqueio persistente protege contra gravações tardias. Os testes em SQLite temporário cobrem os casos corrigidos, registros incompatíveis, isolamento e resíduos. A verificação é lógica e não mede eliminação física em páginas SQLite, WAL ou backups. [Exclusão](testes/testar_exclusao_memoria_offline.py) · [Auditoria](testes/testar_auditoria_exclusao_offline.py) · [Bloqueio persistente](testes/testar_barreira_persistente_offline.py)
- A interface depende de OIDC, vínculos autorizados e chave HMAC estável. Os testes offline simulam identidades e exercitam o bloqueio quando a configuração falta. O login com provedor real e a exclusão pela interface nesse ambiente continuam sem validação de ponta a ponta. [Instalação e configuração](LEIA-ME.md#interface-autenticada)

## Conclusão

O protótipo demonstrou instrução estruturada com consultas auditadas e recuperação das duas complementações. A terceira rodada chegou a 13/14 casos integrais, com 68/70 campos coincidentes e aprovação técnica de 14/14 pela barreira. A divergência de 0106 segue documentada. A avaliação histórica, a rodada de memória, os testes simulados e as estimativas medem aspectos diferentes. O ponto de conferência humana permanece antes da decisão administrativa.

Para a entrega, falta a revisão final do conteúdo do repositório ou ZIP e a publicação autorizada. A validação OIDC de ponta a ponta requer um provedor real configurado.

---

## Execução final validada — 22/11/2026

Esta seção registra a execução real do lote final, preservada em
`resultados/lote_final_14_20261122T211104Z/`.

| Indicador | Resultado |
|---|---:|
| Casos concluídos | 14/14 |
| Chamadas lógicas ao modelo | 12 |
| Tokens de entrada | 140102 |
| Tokens de saída | 7151 |
| Total de tokens | 147253 |
| Duração total | 121.465325 segundos |
| Custo estimado | US$ 0.01246789 |
| Custo efetivamente faturado | Não verificado |

### Distribuição dos registros

- Dez análises iniciais realizadas pelo modelo.
- Duas diligências locais sem chamada ao modelo.
- Duas complementações realizadas pelo modelo, com retomada das sessões.

Os 14 registros receberam status `conferida`, indicando conferência
automatizada. Esse status não representa aprovação administrativa.

A revisão humana permanece obrigatória.

### Métricas e limitações

As métricas do lote final incluem tokens, duração e custo estimado.
O custo apresentado foi calculado com as tarifas declaradas no executor
e não corresponde a faturamento confirmado pela OpenAI.

Os contadores detalhados de cache não foram preservados nos JSONs
resumidos do lote final. Portanto, a decomposição do custo final
por categoria de cache não pode ser reproduzida integralmente
a partir desses arquivos.

As execuções históricas possuem cobertura variável de
métricas. Valores não registrados não foram estimados
retroativamente.

### Evidências históricas complementares

O documento `documentacao/EVIDENCIAS_COMPLEMENTARES.md` consolida
34 registros históricos examinados:

- 25 registros com métricas;
- 34 registros com recomendações preservadas;
- 29 registros com auditoria de ferramentas.

O verificador reproduzível comparou os 34 registros com
os JSONs de origem: 34 encontrados e nenhuma divergência.
Há métricas de tokens e cache em 25 fontes, duração em 29,
recomendação em 34 e trilha de ferramenta em 29. Nenhuma
das 34 fontes registra custo histórico. A duração de
12,564 s de DIA-2026-0111 corresponde ao campo
`duracao_segundos_executor`; `duracao_segundos_persistida`
e `metricas.duration` registram 11,895886 s. O relatório
da auditoria está em
`resultados/auditoria_entrega_final_20261122.json`.

Os registros detalhados das rodadas anteriores incluem recomendações,
verificações, chamadas de ferramentas e resultados da barreira,
conforme a disponibilidade de cada arquivo.

Essas evidências são identificadas como históricas.
Não foram atribuídas indevidamente à execução
final de 22/11/2026.

Os JSONs do lote final preservam resultados resumidos.
A trilha detalhada integral dessa execução não está
comprovada nesses arquivos.

Os 14 registros finais não armazenam recomendação,
chamadas de ferramentas ou os detalhes internos da
barreira. Não foram associados resultados históricos
ao lote final. Os contadores de cache também não foram
preservados por chamada. A soma das durações por caso é
112,882795 s e a duração total registrada no manifesto é
121,465325 s; a diferença de 8,582530 s é apenas a
diferença aritmética entre esses campos, sem medição
independente da orquestração. Os tokens e custos estimados
por caso somam os totais declarados no manifesto. O custo
faturado não foi consultado.

Os resultados históricos e as execuções interrompidas
permanecem preservados separadamente, sem sobrescrita.
