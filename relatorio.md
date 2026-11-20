# Relatorio tecnico final - Desafio 01

**Projeto:** Instrucao de pedidos de diarias com agentes de IA
**Framework:** Agno
**Modelo utilizado:** gpt-5.6-luna
**Ambiente:** Python no Windows, com PowerShell
**Natureza:** Experimento academico com dados e norma hipoteticos

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

## 3. Arquitetura implementada

A solucao utiliza:

- Framework Agno para orquestracao do agente.
- Modelo de linguagem gpt-5.6-luna.
- Quatro ferramentas de verificacao:
  verificar_cadastro, verificar_calculo,
  verificar_prestacoes e verificar_orcamento.
- Funcoes Python deterministicas para consultas e calculos.
- Pydantic para estruturar e validar a instrucao.
- Auditoria das chamadas efetivamente executadas.
- Barreira independente de verificacao normativa.
- Filtro para reduzir exposicao de dados pessoais.
- Persistencia SQLite para historico e memoria.
- Interface Streamlit e registro de revisao humana.

A barreira verifica consistencia dos resultados,
ferramentas obrigatorias, erros, argumentos e calculos
antes de liberar a instrucao para revisao humana.

## 4. Processo de instrucao

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

## 5. Metodologia de avaliacao

Foram avaliados 14 pedidos em tres rodadas.

A avaliacao contra o gabarito considerou acertos
integrais por pedido e correspondencia de campos.

Separadamente, a barreira independente verificou
a consistencia tecnica e normativa das instrucoes.

As rodadas foram preservadas para permitir comparacao,
sem substituir resultados anteriores.

## 6. Resultados das tres rodadas

| Indicador | Inicial | Rodada 2 | Rodada 3 |
|---|---:|---:|---:|
| Casos corretos | 8/14 | 13/14 | 13/14 |
| Acuracia por caso | 57,14% | 92,86% | 92,86% |
| Campos corretos | 61/70 | 68/70 | 68/70 |
| Acuracia por campo | 87,14% | 97,14% | 97,14% |

A terceira rodada manteve os indicadores da segunda.
A barreira tecnica aprovou 14/14 instrucoes na
terceira rodada, resultado distinto da concordancia
de 13/14 com o gabarito.

## 7. Divergencia normativa - DIA-2026-0106

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

## 8. Experimentos de memoria

Foram executados tres cenarios com dois turnos cada.

| Cenario | Duracao media | Tokens turno 1 | Tokens turno 2 |
|---|---:|---:|---:|
| A - Sem memoria | 11,761 s | 9834 | 9855 |
| B - Historico de sessao | 12,056 s | 9896 | 16148 |
| C - Historico e memoria de usuario | 12,158 s | 13893 | 17745 |

Todas as seis execucoes foram concluidas, com quatro
ferramentas auditadas e barreira aprovada.

Os cenarios B e C apresentaram persistencia SQLite
verificada. Tambem foram realizados testes de exclusao
de memoria em ambiente controlado.

Os resultados mostram maior consumo de tokens nos
turnos com historico acumulado, mas a amostra nao
permite concluir superioridade geral de uma estrategia.

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

A configuracao paralela nao comprova, isoladamente,
execucao simultanea das ferramentas. Como houve
uma execucao por modo, nao ha evidencia estatistica
para generalizar a diferenca de desempenho.

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

## 11. Seguranca e revisao humana

Foram adotados controles para:

- Reduzir a exposicao de dados pessoais ao modelo.
- Evitar a alteracao de identificadores confiaveis.
- Conferir as ferramentas efetivamente executadas.
- Rejeitar respostas com erros ou calculos divergentes.
- Estruturar a instrucao e verificar sua consistencia.
- Preservar evidencias para auditoria.
- Manter a decisao administrativa sob responsabilidade humana.

O agente nao realiza autorizacao nem pagamento.

## 12. Limitacoes

- O projeto utiliza dados e norma hipoteticos.
- A concordancia com o gabarito nao mede, isoladamente,
  a conformidade juridica de cada recomendacao.
- A divergencia do pedido 0106 permanece documentada.
- Os experimentos de memoria tiveram dois turnos
  por cenario.
- O experimento de paralelismo teve apenas uma
  execucao por configuracao.
- Os quatro testes de falhas foram simulacoes em memoria.
- Nao foi consolidado custo monetario sem tarifa
  e metricas financeiras verificadas.
- A validacao automatica nao substitui revisao humana.

## 13. Evidencias principais

- `desenho.md`
- `resultados/avaliacao_gabarito_rodada_inicial.json`
- `resultados/avaliacao_gabarito_rodada2_final.json`
- `resultados/avaliacao_gabarito_rodada3.json`
- `resultados/ANALISE_DIVERGENCIA_0106.md`
- `resultados/experimentos_memoria/comparacoes/resumo_comparativo.json`
- `resultados/experimento_paralelismo/RELATORIO_COMPARATIVO.md`
- `resultados/experimento_paralelismo/DIA-2026-0101_sequencial.json`
- `resultados/experimento_paralelismo/DIA-2026-0101_paralelo.json`

## 14. Conclusao

O projeto demonstrou a viabilidade de utilizar um
agente Agno para apoiar a instrucao de pedidos de
diarias com ferramentas deterministicas, validacao
estruturada, memoria opcional e controles independentes.

A concordancia integral com o gabarito evoluiu
de 57,14% para 92,86%, enquanto a acuracia por
campo passou de 87,14% para 97,14%.

Os testes de falhas demonstraram bloqueio das
inconsistencias simuladas. A decisao administrativa
final continua reservada ao responsavel humano.

O projeto deve passar por auditoria final de
dependencias, documentacao e dados sensiveis
antes da publicacao no GitHub.
