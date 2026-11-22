# Experimento de memória nas complementações 0111 e 0112

Projeto individual de Yasmine Lino Franco.

Cada combinação usou SQLite e chave HMAC temporários próprios. Em A, somente a trilha administrativa usou SQLite. Em B e C, o Agno também persistiu runs com limite de três. C habilitou atualização de memória pessoal.

O primeiro turno é uma diligência local. Portanto, não há tokens do modelo nesse turno nem conversa anterior do modelo para recuperar no segundo. O resumo administrativo é recuperado da mesma sessão em todos os cenários. A memória pessoal, quando gerada, é contabilizada sem exportar seu conteúdo.

| Pedido | Cenário | Turno | Status | Chamadas HTTP observadas | Entrada | Saída | Total | Tempo (s) | USD estimado | Barreira |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| DIA-2026-0111 | A | 1 | conferido | 0 | — | — | — | 0.234553 | — | aprovada |
| DIA-2026-0111 | A | 2 | conferido | 5 | 11453 | 579 | 12032 | 9.974306 | 0.00151835 | aprovada |
| DIA-2026-0111 | B | 1 | conferido | 0 | — | — | — | 0.148081 | — | aprovada |
| DIA-2026-0111 | B | 2 | erro | 2 | 4120 | 33 | 4153 | 2.377289 | 0.00012308 | nao_avaliada |
| DIA-2026-0111 | C | 1 | conferido | 0 | — | — | — | 0.147594 | — | aprovada |
| DIA-2026-0111 | C | 2 | conferido | 6 | 12705 | 580 | 13285 | 7.938941 | 0.00180848 | aprovada |
| DIA-2026-0112 | A | 1 | conferido | 0 | — | — | — | 0.21678 | — | aprovada |
| DIA-2026-0112 | A | 2 | conferido | 5 | 11260 | 554 | 11814 | 8.432 | 0.00104220 | aprovada |
| DIA-2026-0112 | B | 1 | conferido | 0 | — | — | — | 0.146741 | — | aprovada |
| DIA-2026-0112 | B | 2 | erro | 1 | 2026 | 16 | 2042 | 1.472618 | 0.00006026 | nao_avaliada |
| DIA-2026-0112 | C | 1 | conferido | 0 | — | — | — | 0.15393 | — | aprovada |
| DIA-2026-0112 | C | 2 | conferido | 6 | 12523 | 578 | 13101 | 8.243325 | 0.00135670 | aprovada |

Tarifa padrão consultada em 22/11/2026. [GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna)

A estimativa usa apenas o consumo reportado, sem descontos, impostos ou acréscimos não informados. O custo faturado permanece indisponível. Requisições recusadas ou sem métricas ficam sem tokens e custo. A contagem HTTP registra tentativas observadas no cliente; uma tentativa sem resposta não comprova processamento no provedor.

Os JSONs individuais trazem estado de validação, sessão, titular sintético, correção e inventário do contexto capturado, sem mensagem integral, credencial ou memória pessoal bruta.
