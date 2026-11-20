# LEIA-ME - Desafio 1 IA - Agentes

**Projeto:** Instrução de Pedidos de Diárias com Agno

## 1. Autoria

| Campo | Informação |
|---|---|
| Autora | Yasmine Lino Franco |
| Curso | FIC - DEV |
| Atividade | Desafio 1 IA - Agentes |
| Modalidade | Projeto individual |

## 2. Apresentação da entrega

Este projeto implementa um agente de inteligência artificial
para auxiliar a instrução de pedidos de diárias, utilizando
dados hipotéticos, ferramentas determinísticas, regras normativas,
memória e conferência humana.

O agente não substitui a decisão administrativa.

A documentação principal está em README.md.

## 3. Arquivos principais

| Arquivo ou pasta | Conteúdo |
|---|---|
| README.md | Apresentação e instruções de execução |
| desenho.md | Processo, PEAS, estimativas e autonomia |
| relatorio.md | Testes, medições, divergências e conclusões |
| agente.py | Configuração do agente Agno |
| ferramentas.py | Consultas e cálculos |
| modelos.py | Estrutura Pydantic |
| barreira_validacao.py | Verificações independentes |
| app.py | Interface Streamlit |
| dados/ | Dados hipotéticos |
| avaliacao/gabarito.json | Referência para avaliação externa |
| testes/ | Scripts de testes |
| resultados/ | Evidências das execuções |

## 4. Preparação

Requisitos:

- Python 3.10 ou superior.
- Chave de API OpenAI para execuções com modelo.
- PowerShell para os comandos apresentados.

Na raiz do projeto:

    py -m venv .venv

    .\.venv\Scripts\python.exe -m pip install -r requirements.txt

Crie o arquivo .env com base em .env.example e configure
OPENAI_API_KEY com sua própria chave.

Não publique credenciais.

## 5. Demonstração ao professor

### 5.1 Testar as ferramentas sem API

    .\.venv\Scripts\python.exe testes/testar_ferramentas.py

Resultado observado na última execução:

- Cadastro: 4/4.
- Histórico: 3/3.
- Cálculo: 2/2.
- Orçamento: 2/2.
- Total: 11/11 testes aprovados.

### 5.2 Executar um pedido com o agente

    .\.venv\Scripts\python.exe testes/executar_pedido.py DIA-2026-0102

Essa execução utiliza a API OpenAI e pode gerar custo.

### 5.3 Executar a interface

    .\.venv\Scripts\python.exe -m streamlit run app.py

A interface permite visualizar a instrução, conferir as
verificações e fundamentos, editar a minuta e registrar
a decisão humana.

## 6. Resultados principais

Foram avaliados 12 pedidos e duas complementações.

| Indicador | Resultado |
|---|---:|
| Casos coincidentes com o gabarito na rodada inicial | 8/14 |
| Casos coincidentes com o gabarito na rodada final | 13/14 |
| Campos coincidentes com o gabarito | 68/70 |
| Execuções aprovadas pela barreira na terceira rodada | 14/14 |
| Verificações de falhas controladas | 22/22 |

A divergência do pedido DIA-2026-0106 foi preservada e
explicada em resultados/ANALISE_DIVERGENCIA_0106.md.

A aprovação da barreira não equivale à coincidência
integral com o gabarito.

## 7. Evidências complementares

- resultados/avaliacao_gabarito_rodada_inicial.json
- resultados/avaliacao_gabarito_rodada2_final.json
- resultados/avaliacao_gabarito_rodada3.json
- resultados/experimentos_memoria/comparacoes/resumo_comparativo.json
- resultados/experimento_paralelismo/RELATORIO_COMPARATIVO.md
- resultados/ANALISE_DIVERGENCIA_0106.md

Os resultados são referentes às execuções registradas
e não representam garantia de desempenho futuro.

## 8. Memória e privacidade

O projeto inclui experimentos com e sem memória persistente,
além de testes de eliminação de sessões, execuções e memórias.

Os bancos SQLite locais não são enviados ao GitHub.

A conferência humana permanece obrigatória.

## 9. GitHub e ZIP acadêmico

O repositório GitHub é destinado ao código, aos dados
hipotéticos necessários, à documentação e às evidências
revisadas.

O ZIP acadêmico final será montado a partir da pasta
local completa do projeto e deverá incluir os documentos
oficiais e exemplos originais do professor, preservados em
material_professor/.

O ZIP não deverá conter:

- Arquivo .env com credenciais.
- Ambientes virtuais.
- Chaves de API.
- Caches e arquivos temporários.

Os bancos e registros locais serão revisados antes da
montagem do pacote final.

## 10. Limitações e responsabilidade

O sistema auxilia a instrução administrativa, mas não
autoriza pagamentos.

As medições são específicas do exercício. A divergência
do pedido DIA-2026-0106 permanece documentada.

O uso em ambiente real exigiria revisão normativa,
proteção adicional de dados e validação institucional.
