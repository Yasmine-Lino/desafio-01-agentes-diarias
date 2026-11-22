# Compara??o final de mem?ria ? 0111 e 0112

A e C v?m da rodada real 8.10-D, e B vem da valida??o real 8.10-F. As tentativas anteriores ficam preservadas.

| Pedido | Modo | Dilig?ncia local (s) | Retomada (s) | Chamadas an?lise / mem?ria | Tokens entrada / sa?da / total | USD estimado | Barreira |
|---|---|---:|---:|---:|---:|---:|---|
| [DIA-2026-0111](../experimentos_memoria_0111_0112_retomada_8_10_D/DIA-2026-0111_A.json) | A | 0.235 | 9.974 | 5 / 0 | 11453 / 579 / 12032 | 0.00151835 | aprovada |
| [DIA-2026-0111](DIA-2026-0111_B.json) | B | 0.149 | 9.483 | 5 / 0 | 11453 / 537 / 11990 | 0.00087616 | aprovada |
| [DIA-2026-0111](../experimentos_memoria_0111_0112_retomada_8_10_D/DIA-2026-0111_C.json) | C | 0.148 | 7.939 | 5 / 1 | 12705 / 580 / 13285 | 0.00180848 | aprovada |
| [DIA-2026-0112](../experimentos_memoria_0111_0112_retomada_8_10_D/DIA-2026-0112_A.json) | A | 0.217 | 8.432 | 5 / 0 | 11260 / 554 / 11814 | 0.00104220 | aprovada |
| [DIA-2026-0112](DIA-2026-0112_B.json) | B | 0.157 | 8.730 | 5 / 0 | 11260 / 586 / 11846 | 0.00093110 | aprovada |
| [DIA-2026-0112](../experimentos_memoria_0111_0112_retomada_8_10_D/DIA-2026-0112_C.json) | C | 0.154 | 8.243 | 5 / 1 | 12523 / 578 / 13101 | 0.00135670 | aprovada |

As seis dilig?ncias foram locais e consumiram zero chamadas. As seis retomadas consolidadas recomendaram apto_para_autorizacao.

A n?o persistiu runs. B e C persistiram o run da retomada. A dilig?ncia inicial n?o criou hist?rico de conversa, portanto n?o houve replay. C fez uma chamada de atualiza??o de mem?ria por pedido, com zero mem?rias pessoais persistidas e zero uso de mem?ria pessoal registrado no contexto.

Os valores usam os tokens reportados pelo provedor e representam estimativas. O faturamento real n?o foi consultado.

[Primeira tentativa](../experimentos_memoria_0111_0112/RELATORIO.md) ? [Rodada 8.10-D](../experimentos_memoria_0111_0112_retomada_8_10_D/RELATORIO.md) ? [Rodada B 8.10-F](RELATORIO.md)
