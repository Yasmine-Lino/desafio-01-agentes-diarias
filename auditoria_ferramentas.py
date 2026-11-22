import csv
import json
from pathlib import Path

from ferramentas import (
    consultar_servidor,
    consultar_historico,
    calcular_diarias,
    consultar_saldo,
)

BASE = Path(__file__).resolve().parent
DADOS = BASE / "dados"

pedidos = json.loads(
    (DADOS / "pedidos.json").read_text(encoding="utf-8-sig")
)

por_numero = {p["numero"]: p for p in pedidos}

resultados = []


def verificar(nome, condicao, detalhe=""):
    aprovado = bool(condicao)
    resultados.append(aprovado)
    print(
        f"{'OK' if aprovado else 'FALHOU'} "
        f"| {nome}"
        + (f" | {detalhe}" if detalhe else "")
    )


print("=" * 65)
print("AUDITORIA INTEGRADA - DESAFIO 01")
print("=" * 65)

# 1. Conferencia cadastral do pedido 0112
pedido = por_numero["DIA-2026-0112"]
servidor = consultar_servidor(pedido["matricula"])

cadastro_compativel = (
    servidor.get("encontrado") is True
    and servidor.get("nome", "").strip().casefold()
        == pedido["nome"].strip().casefold()
)

verificar(
    "0112 - Divergencia cadastral identificada",
    not cadastro_compativel
)

# 2. Prestacao de contas vencida do pedido 0108
pedido = por_numero["DIA-2026-0108"]

historico = consultar_historico(
    pedido["matricula"],
    pedido["data_partida"][:7]
)

verificar(
    "0108 - Prestacao de contas vencida",
    historico.get("possui_prestacao_vencida") is True
)

# 3. Limite mensal do pedido 0109
pedido = por_numero["DIA-2026-0109"]

calculo = calcular_diarias(
    pedido["matricula"],
    pedido["destino_uf"],
    pedido["data_partida"],
    pedido["data_retorno"],
    pedido["data_partida"][:7],
    data_pedido=pedido["data_pedido"],
)

verificar(
    "0109 - Limite mensal excedido",
    calculo.get("limite_mensal_atendido") is False,
    f"Total projetado: {calculo.get('total_projetado_mes')}"
)

# 4. Conferencia financeira do pedido 0110
pedido = por_numero["DIA-2026-0110"]

calculo = calcular_diarias(
    pedido["matricula"],
    pedido["destino_uf"],
    pedido["data_partida"],
    pedido["data_retorno"],
    pedido["data_partida"][:7],
    data_pedido=pedido["data_pedido"],
)

orcamento = consultar_saldo(
    pedido["matricula"],
    calculo.get("valor_total", 0)
)

verificar(
    "0110 - Saldo insuficiente",
    orcamento.get("saldo_suficiente") is False
)

# 5. Protecao de dados pessoais
servidor = consultar_servidor("200941")

verificar(
    "Cadastro - CPF e email nao retornados",
    "cpf" not in servidor and "email" not in servidor
)

print("=" * 65)
print(
    f"RESULTADO FINAL: "
    f"{sum(resultados)}/{len(resultados)} verificacoes aprovadas"
)
print("Nenhuma chamada a API realizada.")
print("Gabarito nao acessado.")
