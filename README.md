# Desafio 1 IA - Agentes

**Projeto:** Instru??o de Pedidos de Di?rias com Agentes de IA
**Autora:** Yasmine Lino Franco
**Curso:** FIC - DEV
**Modalidade:** Individual

## 1. Apresenta??o

Projeto acad?mico que utiliza o framework Agno para auxiliar a
instru??o de pedidos de di?rias com base em regras normativas,
consultas a dados hipot?ticos e confer?ncia humana.

O agente produz uma instru??o estruturada com verifica??es,
quantidade e valor das di?rias, recomenda??o e minuta de despacho.

A decis?o final pertence ao ordenador de despesa.

## 2. Objetivos

- Modelar o processo administrativo com o quadro PEAS.
- Implementar quatro ferramentas de consulta e c?lculo.
- Produzir sa?da estruturada com Pydantic.
- Configurar limites de execu??o e prote??o de dados pessoais.
- Aplicar barreira independente de valida??o.
- Implementar mem?ria persistente e rotina de elimina??o.
- Comparar os resultados com um gabarito externo.
- Medir tempo, tokens e comportamento em situa??es de falha.
- Disponibilizar interface Streamlit para confer?ncia humana.

## 3. Tecnologias

- Python
- Agno
- OpenAI
- Pydantic
- Streamlit
- SQLite
- python-dotenv

As vers?es utilizadas est?o em requirements.txt.

## 4. Funcionamento

O sistema recebe um pedido de di?rias e consulta quatro ferramentas:

1. Verifica??o do cadastro do servidor.
2. C?lculo da quantidade e do valor das di?rias.
3. Verifica??o de hist?rico e presta??es de contas.
4. Verifica??o de disponibilidade or?ament?ria.

O agente utiliza dados fornecidos pelo pedido e pelas ferramentas,
sem autoriza??o para inventar valores ou informa??es cadastrais.

A resposta ? organizada em um modelo Pydantic. Antes de ser exibida
ao conferente, uma barreira em c?digo verifica sua consist?ncia.

A aplica??o tamb?m permite tratar dilig?ncias e complementa??es,
utilizando sess?es e mem?ria persistente quando configuradas.

## 5. Arquitetura e arquivos

| Arquivo ou pasta | Finalidade |
|---|---|
| agente.py | Configura??o do agente Agno |
| ferramentas.py | Consultas e c?lculos determin?sticos |
| modelos.py | Contrato de sa?da estruturada |
| barreira_validacao.py | Valida??o independente |
| seguranca.py | Prote??o de dados pessoais |
| persistencia_sessoes.py | Gest?o e persist?ncia de sess?es |
| validacao_normativa.py | Verifica??es normativas |
| validacao_recomendacao.py | Confer?ncia das recomenda??es |
| complementacoes.py | Tratamento de complementa??es |
| app.py | Interface Streamlit |
| dados/ | Acervo hipot?tico do exerc?cio |
| avaliacao/ | Gabarito externo de avalia??o |
| testes/ | Testes e experimentos |
| resultados/ | Evid?ncias das execu??es |
| desenho.md | Processo, PEAS e estimativas |
| relatorio.md | Medi??es, falhas e conclus?es |

O gabarito ? usado para avalia??o externa e n?o deve ser fornecido
ao agente durante a gera??o das instru??es.

## 6. Prepara??o do ambiente

Requisitos:

- Windows com PowerShell, para os comandos abaixo.
- Python 3.10 ou superior.
- Acesso ? API OpenAI.
- Acervo hipot?tico presente na pasta dados/.

Na raiz do projeto, crie o ambiente virtual:

    py -m venv .venv

Instale as depend?ncias:

    .\.venv\Scripts\python.exe -m pip install -r requirements.txt

Crie o arquivo .env com base no .env.example e configure a vari?vel
OPENAI_API_KEY com sua pr?pria chave.

O arquivo .env cont?m credenciais locais e n?o deve ser publicado.

## 7. Executar o sistema

Para abrir a interface Streamlit:

    .\.venv\Scripts\python.exe -m streamlit run app.py

Para executar o m?dulo de configura??o do agente:

    .\.venv\Scripts\python.exe agente.py

A aplica??o utiliza os dados do exerc?cio presentes em dados/.

Chamadas reais ao modelo podem consumir cr?ditos da API.

## 8. Executar testes

Teste determin?stico das ferramentas:

    .\.venv\Scripts\python.exe testes/testar_ferramentas.py

Teste de um pedido com chamada ao modelo:

    .\.venv\Scripts\python.exe testes/executar_pedido.py DIA-2026-0102

Execu??o da terceira rodada para um pedido:

    .\.venv\Scripts\python.exe testes/executar_rodada3.py DIA-2026-0102

Outros scripts est?o dispon?veis em testes/, incluindo experimentos
de mem?ria, paralelismo e complementa??es.

## 9. Avalia??o dos resultados

Foram avaliados 12 pedidos e duas complementa??es, totalizando
14 casos.

| Indicador | Resultado |
|---|---:|
| Coincid?ncia integral inicial com o gabarito | 8/14 (57,14%) |
| Coincid?ncia integral final com o gabarito | 13/14 (92,86%) |
| Coincid?ncia dos campos avaliados | 68/70 (97,14%) |
| Aprova??o da barreira t?cnica na terceira rodada | 14/14 |
| Verifica??es de falhas controladas | 22/22 |

A aprova??o pela barreira t?cnica n?o significa coincid?ncia
integral com o gabarito.

O pedido DIA-2026-0106 apresentou diverg?ncia de recomenda??o,
relacionada ? interpreta??o da urg?ncia e ? necessidade de
autoriza??o escrita.

Essa diverg?ncia foi preservada e documentada em
resultados/ANALISE_DIVERGENCIA_0106.md.

## 10. Experimentos adicionais

### Mem?ria

Foram comparadas tr?s configura??es:

- A: sem mem?ria persistente.
- B: com hist?rico de sess?o.
- C: com hist?rico e mem?ria do usu?rio.

As seis execu??es do experimento foram conclu?das e aprovadas
pela barreira t?cnica.

Evid?ncia:
resultados/experimentos_memoria/comparacoes/resumo_comparativo.json

### Paralelismo

Foi realizada uma compara??o entre execu??o sequencial e
configura??o com chamadas paralelas.

Tempo observado:

- Sequencial: 10,937 segundos.
- Paralelo habilitado: 6,622 segundos.

A redu??o observada foi de aproximadamente 39,45% no tempo
da execu??o analisada.

O experimento representa uma compara??o pontual e n?o comprova
concorr?ncia efetiva nem desempenho generaliz?vel.

Evid?ncia:
resultados/experimento_paralelismo/RELATORIO_COMPARATIVO.md

### Falhas controladas

Foram realizadas 22 verifica??es em quatro situa??es simuladas:

- Falha de ferramenta.
- Aus?ncia de consulta obrigat?ria.
- Diverg?ncia no valor total.
- Diverg?ncia na quantidade de di?rias.

As verifica??es confirmaram a atua??o da barreira nos cen?rios
simulados. Os detalhes est?o em relatorio.md.

## 11. Seguran?a e confer?ncia humana

O sistema utiliza dados hipot?ticos fornecidos para o exerc?cio.

A chave OPENAI_API_KEY deve permanecer no arquivo .env,
que est? exclu?do do controle de vers?o.

O agente auxilia a instru??o, mas n?o autoriza pagamentos.
A decis?o final permanece com o respons?vel humano.

A interface permite conferir os fundamentos, editar a minuta
e registrar a decis?o do conferente.

Os bancos SQLite locais e os logs n?o s?o publicados no GitHub.

## 12. Documenta??o

- desenho.md: processo, quadro PEAS, confiabilidade composta,
  estimativa de custos por passos e quadrante de autonomia.
- relatorio.md: resultados, diverg?ncias, falhas e conclus?es.
- resultados/: arquivos das medi??es e avalia??es.
- LEIA-ME.md: orienta??es complementares de entrega,
  ap?s sua cria??o.

Os documentos originais do professor permanecem em
material_professor/ para inclus?o no ZIP acad?mico final.

O reposit?rio p?blico cont?m o c?digo desenvolvido, os dados
hipot?ticos necess?rios, o gabarito de avalia??o e as
evid?ncias textuais revisadas.

## 13. Limita??es

- Os resultados foram medidos no ambiente e nos casos do exerc?cio.
- O desempenho pode variar entre execu??es e ambientes.
- A diverg?ncia do pedido DIA-2026-0106 permanece documentada.
- O custo monet?rio n?o foi confirmado em todas as medi??es.
- A decis?o administrativa n?o ? automatizada.
- Os bancos locais de mem?ria n?o integram o reposit?rio p?blico.

## 14. Autoria

Yasmine Lino Franco

FIC - DEV

Desafio 1 IA - Agentes

Projeto individual desenvolvido para fins acad?micos.
