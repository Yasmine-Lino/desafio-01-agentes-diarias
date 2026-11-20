# Experimento - Ferramentas sequenciais versus paralelas

## 1. Objetivo

Comparar duas execucoes reais do agente Agno de instrucao
de pedidos de diarias, utilizando o mesmo pedido e modelo,
com e sem a habilitacao de chamadas paralelas de ferramentas.

## 2. Configuracao

- Pedido: DIA-2026-0101
- Modelo: gpt-5.6-luna
- Framework: Agno
- Memoria: desativada nos dois modos
- Modo sequencial: parallel_tool_calls=False
- Modo paralelo: parallel_tool_calls=True
- Ferramentas esperadas: quatro
- Validacao: barreira normativa independente
- Execucoes: uma por configuracao

## 3. Resultados

| Indicador | Sequencial | Paralelo |
|---|---:|---:|
| Tempo (segundos) | 10.937 | 6.622 |
| Tokens de entrada | 10782 | 4202 |
| Tokens de saida | 617 | 525 |
| Tokens totais | 11399 | 4727 |
| Ferramentas executadas | 4 | 4 |
| Barreira normativa | Aprovada | Aprovada |
| Erros nas ferramentas | 0 | 0 |

## 4. Comparacao

- Reducao observada no tempo: 39.45%
- Diferenca absoluta no tempo: 4.315 segundos
- Reducao observada nos tokens: 58.53%
- Diferenca absoluta nos tokens: 6672
- Resultados principais: equivalentes

## 5. Resultado da instrucao

- Recomendacao: apto_para_autorizacao
- Quantidade de diarias: 3.5
- Valor total: R$ 980.00
- Quatro ferramentas auditadas em cada execucao
- Barreira normativa independente aprovada
- Decisao administrativa final permanece humana

## 6. Limitacoes

A habilitacao de parallel_tool_calls=True nao comprova,
isoladamente, que as ferramentas foram executadas
simultaneamente.

Nao foram coletadas evidencias temporais suficientes
para comprovar sobreposicao real entre as ferramentas.

Foi realizada apenas uma execucao por configuracao.
Portanto, as diferencas observadas nao representam
uma estimativa estatistica de desempenho.

O consumo de tokens tambem pode variar entre execucoes
do mesmo modelo devido ao comportamento da geracao.

As metricas de custo retornadas pelo modelo nao
informaram um valor monetario consolidado.
Nao foi estimado custo financeiro sem tarifa verificada.

## 7. Evidencias preservadas

- DIA-2026-0101_sequencial.json
- DIA-2026-0101_paralelo.json

Os arquivos originais permanecem inalterados.

## 8. Conclusao

Nas execucoes observadas, a configuracao paralela
apresentou menor tempo e menor consumo de tokens,
mantendo resultados principais equivalentes e
aprovacao na barreira normativa.

O experimento demonstra o efeito observado da
configuracao, sem afirmar causalidade exclusiva,
simultaneidade comprovada ou superioridade geral.
