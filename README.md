# Desafio 1 IA - Agentes

**Projeto:** Instrução de Pedidos de Diárias com Agno

## 1. Autoria

| Campo | Informação |
|---|---|
| Autora | Yasmine Lino Franco |
| Curso | FIC - DEV |
| Atividade | Desafio 1 IA - Agentes |
| Modalidade | Projeto individual |

## 2. Apresentação

Projeto acadêmico que utiliza o framework Agno para auxiliar a
instrução de pedidos de diárias com base em regras normativas,
consultas a dados hipotéticos e conferência humana.

O agente produz uma instrução estruturada com verificações,
quantidade e valor das diárias, recomendação e minuta de despacho.

A decisão final pertence ao ordenador de despesa.

## 3. Objetivos

- Modelar o processo administrativo com o quadro PEAS.
- Implementar quatro ferramentas de consulta e cálculo.
- Produzir saída estruturada com Pydantic.
- Configurar limites de execução e proteção de dados pessoais.
- Aplicar barreira independente de validação.
- Implementar memória persistente e rotina de eliminação.
- Comparar os resultados com um gabarito externo.
- Medir tempo, tokens e comportamento em situações de falha.
- Disponibilizar interface Streamlit para conferência humana.

## 4. Tecnologias

- Python
- Agno
- OpenAI
- Pydantic
- Streamlit
- SQLite
- python-dotenv

As versões utilizadas estão em requirements.txt.

## 5. Funcionamento

O sistema recebe um pedido de diárias e consulta quatro ferramentas:

1. Verificação do cadastro do servidor.
2. Cálculo da quantidade e do valor das diárias.
3. Verificação de histórico e prestações de contas.
4. Verificação de disponibilidade orçamentária.

O agente utiliza dados fornecidos pelo pedido e pelas ferramentas,
sem autorização para inventar valores ou informações cadastrais.

A resposta é organizada em um modelo Pydantic. Antes de ser exibida
ao conferente, uma barreira em código verifica sua consistência.

A aplicação também permite tratar diligências e complementações,
utilizando sessões e memória persistente quando configuradas.

## 6. Arquitetura e arquivos

| Arquivo ou pasta | Finalidade |
|---|---|
| agente.py | Configuração do agente Agno |
| ferramentas.py | Consultas e cálculos determinísticos |
| modelos.py | Contrato de saída estruturada |
| barreira_validacao.py | Validação independente |
| seguranca.py | Proteção de dados pessoais |
| persistencia_sessoes.py | Gestão e persistência de sessões |
| validacao_normativa.py | Verificações normativas |
| validacao_recomendacao.py | Conferência das recomendações |
| complementacoes.py | Tratamento de complementações |
| app.py | Interface Streamlit |
| dados/ | Acervo hipotético do exercício |
| avaliacao/ | Gabarito externo de avaliação |
| testes/ | Testes e experimentos |
| resultados/ | Evidências das execuções |
| desenho.md | Processo, PEAS e estimativas |
| relatorio.md | Medições, falhas e conclusões |

O gabarito é usado para avaliação externa e não deve ser fornecido
ao agente durante a geração das instruções.

## 7. Preparação do ambiente

Requisitos:

- Windows com PowerShell, para os comandos abaixo.
- Python 3.10 ou superior.
- Acesso à API OpenAI.
- Acervo hipotético presente na pasta dados/.

Na raiz do projeto, crie o ambiente virtual:

    py -m venv .venv

Instale as dependências:

    .\.venv\Scripts\python.exe -m pip install -r requirements.txt

Crie o arquivo .env com base no .env.example e configure a variável
OPENAI_API_KEY com sua própria chave.

O arquivo .env contém credenciais locais e não deve ser publicado.

## 8. Executar o sistema

Para abrir a interface Streamlit:

    .\.venv\Scripts\python.exe -m streamlit run app.py

Para executar o módulo de configuração do agente:

    .\.venv\Scripts\python.exe agente.py

A aplicação utiliza os dados do exercício presentes em dados/.

Chamadas reais ao modelo podem consumir créditos da API.

## 9. Executar testes

Teste determinístico das ferramentas:

    .\.venv\Scripts\python.exe testes/testar_ferramentas.py

Teste de um pedido com chamada ao modelo:

    .\.venv\Scripts\python.exe testes/executar_pedido.py DIA-2026-0102

Execução da terceira rodada para um pedido:

    .\.venv\Scripts\python.exe testes/executar_rodada3.py DIA-2026-0102

Outros scripts estão disponíveis em testes/, incluindo experimentos
de memória, paralelismo e complementações.

## 10. Avaliação dos resultados

Foram avaliados 12 pedidos e duas complementações, totalizando
14 casos.

| Indicador | Resultado |
|---|---:|
| Coincidência integral inicial com o gabarito | 8/14 (57,14%) |
| Coincidência integral final com o gabarito | 13/14 (92,86%) |
| Coincidência dos campos avaliados | 68/70 (97,14%) |
| Aprovação da barreira técnica na terceira rodada | 14/14 |
| Verificações de falhas controladas | 22/22 |

A aprovação pela barreira técnica não significa coincidência
integral com o gabarito.

O pedido DIA-2026-0106 apresentou divergência de recomendação,
relacionada à interpretação da urgência e à necessidade de
autorização escrita.

Essa divergência foi preservada e documentada em
resultados/ANALISE_DIVERGENCIA_0106.md.

## 11. Experimentos adicionais

### Memória

Foram comparadas três configurações:

- A: sem memória persistente.
- B: com histórico de sessão.
- C: com histórico e memória do usuário.

As seis execuções do experimento foram concluídas e aprovadas
pela barreira técnica.

Evidência:
resultados/experimentos_memoria/comparacoes/resumo_comparativo.json

### Paralelismo

Foi realizada uma comparação entre execução sequencial e
configuração com chamadas paralelas.

Tempo observado:

- Sequencial: 10,937 segundos.
- Paralelo habilitado: 6,622 segundos.

A redução observada foi de aproximadamente 39,45% no tempo
da execução analisada.

O experimento representa uma comparação pontual e não comprova
concorrência efetiva nem desempenho generalizável.

Evidência:
resultados/experimento_paralelismo/RELATORIO_COMPARATIVO.md

### Falhas controladas

Foram realizadas 22 verificações em quatro situações simuladas:

- Falha de ferramenta.
- Ausência de consulta obrigatória.
- Divergência no valor total.
- Divergência na quantidade de diárias.

As verificações confirmaram a atuação da barreira nos cenários
simulados. Os detalhes estão em relatorio.md.

## 12. Segurança e conferência humana

O sistema utiliza dados hipotéticos fornecidos para o exercício.

A chave OPENAI_API_KEY deve permanecer no arquivo .env,
que está excluído do controle de versão.

O agente auxilia a instrução, mas não autoriza pagamentos.
A decisão final permanece com o responsável humano.

A interface permite conferir os fundamentos, editar a minuta
e registrar a decisão do conferente.

Os bancos SQLite locais e os logs não são publicados no GitHub.

## 13. Documentação

- desenho.md: processo, quadro PEAS, confiabilidade composta,
  estimativa de custos por passos e quadrante de autonomia.
- relatorio.md: resultados, divergências, falhas e conclusões.
- resultados/: arquivos das medições e avaliações.
- LEIA-ME.md: orientações complementares de entrega,
  após sua criação.

Os documentos originais do professor permanecem em
material_professor/ para inclusão no ZIP acadêmico final.

O repositório público contém o código desenvolvido, os dados
hipotéticos necessários, o gabarito de avaliação e as
evidências textuais revisadas.

## 14. Limitações

- Os resultados foram medidos no ambiente e nos casos do exercício.
- O desempenho pode variar entre execuções e ambientes.
- A divergência do pedido DIA-2026-0106 permanece documentada.
- O custo monetário não foi confirmado em todas as medições.
- A decisão administrativa não é automatizada.
- Os bancos locais de memória não integram o repositório público.
