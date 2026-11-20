# LEIA-ME - Desafio 1 IA - Agentes

**Autora:** Yasmine Lino Franco
**Curso:** FIC - DEV
**Modalidade:** Individual
**Projeto:** Instru??o de Pedidos de Di?rias com Agno

## 1. Apresenta??o da entrega

Este projeto implementa um agente de intelig?ncia artificial
para auxiliar a instru??o de pedidos de di?rias, utilizando
dados hipot?ticos, ferramentas determin?sticas, regras normativas,
mem?ria e confer?ncia humana.

O agente n?o substitui a decis?o administrativa.

A documenta??o principal est? em README.md.

## 2. Arquivos principais

| Arquivo ou pasta | Conte?do |
|---|---|
| README.md | Apresenta??o e instru??es de execu??o |
| desenho.md | Processo, PEAS, estimativas e autonomia |
| relatorio.md | Testes, medi??es, diverg?ncias e conclus?es |
| agente.py | Configura??o do agente Agno |
| ferramentas.py | Consultas e c?lculos |
| modelos.py | Estrutura Pydantic |
| barreira_validacao.py | Verifica??es independentes |
| app.py | Interface Streamlit |
| dados/ | Dados hipot?ticos |
| avaliacao/gabarito.json | Refer?ncia para avalia??o externa |
| testes/ | Scripts de testes |
| resultados/ | Evid?ncias das execu??es |

## 3. Prepara??o

Requisitos:

- Python 3.10 ou superior.
- Chave de API OpenAI para execu??es com modelo.
- PowerShell para os comandos apresentados.

Na raiz do projeto:

    py -m venv .venv

    .\.venv\Scripts\python.exe -m pip install -r requirements.txt

Crie o arquivo .env com base em .env.example e configure
OPENAI_API_KEY com sua pr?pria chave.

N?o publique credenciais.

## 4. Demonstra??o ao professor

### 4.1 Testar as ferramentas sem API

    .\.venv\Scripts\python.exe testes/testar_ferramentas.py

Resultado observado na ?ltima execu??o:

- Cadastro: 4/4.
- Hist?rico: 3/3.
- C?lculo: 2/2.
- Or?amento: 2/2.
- Total: 11/11 testes aprovados.

### 4.2 Executar um pedido com o agente

    .\.venv\Scripts\python.exe testes/executar_pedido.py DIA-2026-0102

Essa execu??o utiliza a API OpenAI e pode gerar custo.

### 4.3 Executar a interface

    .\.venv\Scripts\python.exe -m streamlit run app.py

A interface permite visualizar a instru??o, conferir as
verifica??es e fundamentos, editar a minuta e registrar
a decis?o humana.

## 5. Resultados principais

Foram avaliados 12 pedidos e duas complementa??es.

| Indicador | Resultado |
|---|---:|
| Casos coincidentes com o gabarito na rodada inicial | 8/14 |
| Casos coincidentes com o gabarito na rodada final | 13/14 |
| Campos coincidentes com o gabarito | 68/70 |
| Execu??es aprovadas pela barreira na terceira rodada | 14/14 |
| Verifica??es de falhas controladas | 22/22 |

A diverg?ncia do pedido DIA-2026-0106 foi preservada e
explicada em resultados/ANALISE_DIVERGENCIA_0106.md.

A aprova??o da barreira n?o equivale ? coincid?ncia
integral com o gabarito.

## 6. Evid?ncias complementares

- resultados/avaliacao_gabarito_rodada_inicial.json
- resultados/avaliacao_gabarito_rodada2_final.json
- resultados/avaliacao_gabarito_rodada3.json
- resultados/experimentos_memoria/comparacoes/resumo_comparativo.json
- resultados/experimento_paralelismo/RELATORIO_COMPARATIVO.md
- resultados/ANALISE_DIVERGENCIA_0106.md

Os resultados s?o referentes ?s execu??es registradas
e n?o representam garantia de desempenho futuro.

## 7. Mem?ria e privacidade

O projeto inclui experimentos com e sem mem?ria persistente,
al?m de testes de elimina??o de sess?es, execu??es e mem?rias.

Os bancos SQLite locais n?o s?o enviados ao GitHub.

A confer?ncia humana permanece obrigat?ria.

## 8. GitHub e ZIP acad?mico

O reposit?rio GitHub ? destinado ao c?digo, aos dados
hipot?ticos necess?rios, ? documenta??o e ?s evid?ncias
revisadas.

O ZIP acad?mico final ser? montado a partir da pasta
local completa do projeto e dever? incluir os documentos
oficiais e exemplos originais do professor, preservados em
material_professor/.

O ZIP n?o dever? conter:

- Arquivo .env com credenciais.
- Ambientes virtuais.
- Chaves de API.
- Caches e arquivos tempor?rios.

Os bancos e registros locais ser?o revisados antes da
montagem do pacote final.

## 9. Limita??es e responsabilidade

O sistema auxilia a instru??o administrativa, mas n?o
autoriza pagamentos.

As medi??es s?o espec?ficas do exerc?cio. A diverg?ncia
do pedido DIA-2026-0106 permanece documentada.

O uso em ambiente real exigiria revis?o normativa,
prote??o adicional de dados e valida??o institucional.

## 10. Autoria

**Yasmine Lino Franco**
**FIC - DEV**
**Desafio 1 IA - Agentes**

Projeto acad?mico individual.
