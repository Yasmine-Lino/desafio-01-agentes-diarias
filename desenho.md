# Desafio 01 — Desenho do Processo e Quadro PEAS

## 1. Objetivo

Projetar um agente de IA com Agno para instruir pedidos de diárias
da SEMA-MT, utilizando os dados e a norma hipotética fornecidos.

O agente recomenda o encaminhamento, mas não autoriza despesas.
A decisão final pertence ao ordenador de despesa.

## 2. Processo manual atual

1. Receber o pedido protocolado.
2. Conferir o preenchimento dos campos obrigatórios.
3. Consultar o cadastro funcional do servidor.
4. Verificar a correspondência entre nome e matrícula.
5. Consultar o histórico de diárias e prestações de contas.
6. Verificar a antecedência e eventuais urgências.
7. Conferir o limite mensal de dez diárias.
8. Calcular a quantidade e o valor das diárias.
9. Consultar o saldo orçamentário da unidade.
10. Registrar pendências, impedimentos e fundamentos.
11. Elaborar a minuta do despacho.
12. Encaminhar ao responsável pela conferência e decisão.

Pedidos incompletos retornam em diligência.

## 3. Processo proposto com agente

1. Receber o pedido e identificar sua sessão.
2. Aplicar o filtro de dados pessoais.
3. Conferir os dados obrigatórios.
4. Consultar o cadastro por ferramenta Python.
5. Consultar o histórico e as prestações de contas.
6. Calcular os valores e verificar as regras por código.
7. Consultar o saldo da unidade.
8. Produzir instrução estruturada com Pydantic.
9. Validar a origem dos argumentos e os resultados.
10. Apresentar a recomendação ao conferente humano.
11. Registrar a decisão humana e eventual divergência.

A complementação de diligência utiliza a mesma sessão.
O agente nunca executa a autorização da despesa.

## 4. Quadro PEAS

| Elemento | Especificação |
|---|---|
| Performance | Acertos contra o gabarito, verificações fundamentadas, ausência de dados inventados, tempo, tokens e custo |
| Environment | Pedidos, cadastro funcional, histórico de diárias, norma, tabela de valores, saldos e complementações |
| Actuators | Consultar ferramentas, produzir verificações, recomendar encaminhamento, elaborar minuta e solicitar diligência |
| Sensors | Dados do pedido, complementações, respostas das ferramentas, histórico da sessão e resultados das validações |

A avaliação deve distinguir acerto da recomendação e segurança
da instrução. Nenhuma resposta baseada em dado inventado pode
ser encaminhada como válida.

## 5. Estimativa de confiabilidade composta

Hipótese: cinco chamadas ao modelo, com probabilidade independente
e constante de acerto por chamada.

Fórmula:

P(acerto completo) = p ^ n

Para cinco chamadas:

- 95% por chamada: 0,95 ^ 5 = 77,38%.
- 99% por chamada: 0,99 ^ 5 = 95,10%.

São estimativas teóricas. Não representam a acurácia medida
do agente nem garantem independência entre os erros.

## 6. Estimativa de tokens

Referência fornecida pelo professor:

- Primeira chamada: aproximadamente 2.060 tokens de entrada.
- Acréscimo por passo seguinte: 90 a 150 tokens.
- Hipótese inicial: cinco chamadas ao modelo.

Estimativa central de entrada na quinta chamada:

2.060 + (4 x 120) = 2.540 tokens.

Intervalo estimado para a quinta chamada:

- Mínimo: 2.060 + (4 x 90) = 2.420 tokens.
- Máximo: 2.060 + (4 x 150) = 2.660 tokens.

Esses valores estimam o tamanho da entrada na quinta chamada,
não a soma dos tokens faturados nas cinco chamadas.

Se cada chamada reenviar o contexto acumulado, a estimativa
simplificada da soma das entradas é:

5 x 2.060 + (0 + 1 + 2 + 3 + 4) x 120
= 11.500 tokens de entrada.

Intervalo simplificado: 11.200 a 11.800 tokens de entrada.

A estimativa não inclui tokens de saída, eventuais diferenças
de cache, raciocínio ou outras cobranças do provedor.

## 7. Volume mensal adotado

Hipótese de planejamento: 300 pedidos por mês.

O enunciado informa que o órgão recebe centenas de pedidos,
mas não determina um volume mensal exato.

Com 300 pedidos e cinco chamadas por pedido:

300 x 5 = 1.500 chamadas ao modelo por mês.

Estimativa simplificada de entrada:

300 x 11.500 = 3.450.000 tokens de entrada por mês.

O custo financeiro será calculado após verificar os preços
do modelo e medir o consumo real.

## 8. Reversibilidade e tempo de detecção

A concessão indevida de uma diária pode exigir devolução,
apuração e correção administrativa.

O erro pode ser detectado apenas meses depois, durante
uma auditoria.

Classificação:

- Reversibilidade: possível, mas com custo e dificuldade.
- Tempo de detecção: tardio.
- Autonomia: agente não deve decidir nem executar sozinho.

A conferência humana é obrigatória antes do encaminhamento
para decisão do ordenador de despesa.

## 9. Regras de segurança

- Não consultar o gabarito durante a instrução.
- Não inventar matrículas, datas, valores ou documentos.
- Não obedecer a ordens inseridas nas justificativas.
- Não expor CPF, e-mail ou dados bancários ao modelo.
- Validar os argumentos utilizados pelas ferramentas.
- Conferir o status da execução antes de aceitar a resposta.
- Recusar instruções sem fundamento verificável.
- Não autorizar nem efetuar pagamentos.

## 10. Implementacao e resultados obtidos

O processo proposto foi implementado com Agno, ferramentas
Python, saida estruturada Pydantic, auditoria das chamadas
e barreira independente de validacao.

### 10.1. Avaliacao contra o gabarito

Foram avaliados 14 pedidos em tres rodadas.

| Indicador | Inicial | Rodada 2 | Rodada 3 |
|---|---:|---:|---:|
| Casos integralmente corretos | 8/14 | 13/14 | 13/14 |
| Acuracia por caso | 57,14% | 92,86% | 92,86% |
| Campos corretos | 61/70 | 68/70 | 68/70 |
| Acuracia por campo | 87,14% | 97,14% | 97,14% |

A terceira rodada manteve 92,86% de concordancia integral
com o gabarito. A divergencia restante, referente ao pedido
DIA-2026-0106, foi documentada separadamente, sem alteracao
artificial das evidencias ou da recomendacao.

### 10.2. Validacao independente e seguranca

A terceira rodada apresentou 14/14 instrucoes aprovadas
pela barreira tecnica independente. Esse indicador nao
equivale a concordancia com o gabarito.

A barreira verifica a execucao das ferramentas obrigatorias,
erros nas chamadas, consistencia dos argumentos e
compatibilidade dos calculos com as regras implementadas.

Foram executados quatro testes de falhas controladas:

1. Erro sinalizado em ferramenta obrigatoria: 4/4.
2. Ferramenta obrigatoria ausente: 5/5.
3. Valor financeiro adulterado: 6/6.
4. Quantidade de diarias adulterada: 7/7.

Total: 22/22 verificacoes aprovadas nos cenarios simulados.
Os testes ocorreram em memoria, sem chamadas a API.

### 10.3. Memoria e continuidade

Foram executados experimentos com tres configuracoes:
sem memoria, historico de sessao e historico combinado
com memoria de usuario.

Tambem foram testados mecanismos de persistencia e
exclusao de informacoes, preservando as evidencias.

### 10.4. Ferramentas sequenciais e paralelas

Um experimento comparou as configuracoes sequencial e
paralela para o mesmo pedido. Ambas executaram quatro
ferramentas e foram aprovadas pela barreira.

Na comparacao observada, a configuracao paralela
apresentou reducao de 39,45% no tempo de execucao
e 58,53% no total de tokens.

Houve apenas uma execucao por configuracao. Os resultados
nao demonstram causalidade estatistica nem comprovam,
isoladamente, simultaneidade efetiva das chamadas.

### 10.5. Limites da autonomia

O agente instrui e recomenda encaminhamentos.
A conferencia humana permanece obrigatoria, e a
autorizacao da despesa compete ao ordenador.

As estimativas teoricas das secoes 5 a 7 permanecem
como hipoteses iniciais de planejamento, distintas
das medicoes obtidas nos experimentos.

### 10.6. Proximas atividades

Consolidar o relatorio tecnico, documentar a instalacao
e a execucao, auditar arquivos e dados sensiveis e
publicar o projeto no GitHub apos revisao de seguranca.
