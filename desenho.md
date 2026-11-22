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


## 10. Confronto com as medições

A estimativa central de 11.500 tokens de entrada para cinco chamadas pode ser comparada aos 10.782 tokens de entrada do caso sequencial 0101 e aos 11.453 (0111/B) e 11.260 (0112/B) das retomadas com histórico habilitado. Para esses três casos, o observado ficou aproximadamente 6,24%, 0,41% e 2,09% abaixo da estimativa, respectivamente, tomando a estimativa como base. A diligência de 0111 e 0112 ocorreu localmente; nessas duas medições, as cinco chamadas foram da retomada. A configuração paralela e a chamada adicional de atualização de memória em C têm outra composição de passos.

A confiabilidade composta é uma hipótese de planejamento. A métrica observada foi de 13/14 casos integrais contra o gabarito na terceira rodada, com 14/14 instruções aprovadas pela barreira. A divergência em 0106 mostra por que a conferência permanece após a validação técnica e antes do encaminhamento. [Medições, falhas e divergência](relatorio.md)
