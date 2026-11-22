import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from ferramentas import consultar_servidor

testes = [
    ("200941", True),
    ("999999", False),
    ("abc", False),
    ("", False),
]

aprovados = 0

for matricula, esperado in testes:
    resultado = consultar_servidor(matricula)

    encontrado = resultado.get("encontrado") is True

    sem_dados_sensiveis = (
        "cpf" not in resultado
        and "email" not in resultado
    )

    passou = encontrado == esperado and sem_dados_sensiveis

    if passou:
        aprovados += 1

    print(
        f"{'OK' if passou else 'FALHOU'} "
        f"| Matricula: {matricula!r} "
        f"| Encontrado: {encontrado}"
    )

print("=" * 55)
print(f"RESULTADO: {aprovados}/{len(testes)} testes aprovados")
print("Nenhuma chamada a API realizada.")

from ferramentas import consultar_historico, adicionar_dias_uteis
from datetime import date

print("\n=== TESTES DO HISTORICO ===")

casos = [
    ("203648", "2026-11", True),
    ("204317", "2026-11", False),
]

aprovados_historico = 0

for matricula, mes, vencida_esperada in casos:
    resultado = consultar_historico(matricula, mes)

    passou = (
        "erro" not in resultado
        and resultado["possui_prestacao_vencida"] == vencida_esperada
    )

    aprovados_historico += int(passou)

    print(
        f"{'OK' if passou else 'FALHOU'} "
        f"| Matricula: {matricula} "
        f"| Prestacao vencida: "
        f"{resultado.get('possui_prestacao_vencida')}"
    )

prazo = adicionar_dias_uteis(date(2026, 10, 9), 5)
passou_prazo = prazo == date(2026, 10, 16)

aprovados_historico += int(passou_prazo)

print(
    f"{'OK' if passou_prazo else 'FALHOU'} "
    f"| Cinco dias uteis: {prazo}"
)

print("=" * 55)
print(f"RESULTADO HISTORICO: {aprovados_historico}/3")
print("Nenhuma chamada a API realizada.")

from ferramentas import calcular_diarias

print("\n=== TESTES DE CALCULO ===")

teste_0103 = calcular_diarias(
    matricula="203156",
    destino_uf="MT",
    data_partida="2026-11-05",
    data_retorno="2026-11-05",
    mes_referencia="2026-11",
    data_pedido="2026-10-07",
)

ok_0103 = teste_0103.get("quantidade_diarias") == 0.5

print(
    f"{'OK' if ok_0103 else 'FALHOU'} "
    f"| Pedido 0103 | Quantidade: "
    f"{teste_0103.get('quantidade_diarias')}"
)

teste_0105 = calcular_diarias(
    matricula="206230",
    destino_uf="MT",
    data_partida="2026-10-13",
    data_retorno="2026-10-15",
    mes_referencia="2026-10",
    data_pedido="2026-10-08",
)

ok_0105 = (
    teste_0105.get("antecedencia_atendida") is False
    and teste_0105.get("antecedencia_dias") == 5
)

print(
    f"{'OK' if ok_0105 else 'FALHOU'} "
    f"| Pedido 0105 | Antecedencia: "
    f"{teste_0105.get('antecedencia_dias')} dias"
)

total = int(ok_0103) + int(ok_0105)

print("=" * 55)
print(f"RESULTADO CALCULO: {total}/2")
print("Nenhuma chamada a API realizada.")

from ferramentas import consultar_saldo

print("\n=== TESTES DO ORCAMENTO ===")

calculo_0110 = calcular_diarias(
    matricula="205507",
    destino_uf="RO",
    data_partida="2026-11-10",
    data_retorno="2026-11-14",
    mes_referencia="2026-11",
    data_pedido="2026-10-02",
)

if "erro" in calculo_0110:
    print("FALHOU | Calculo do pedido 0110:", calculo_0110)
    ok_0110 = False
else:
    orcamento_0110 = consultar_saldo(
        "205507",
        calculo_0110["valor_total"]
    )

    ok_0110 = (
        "erro" not in orcamento_0110
        and orcamento_0110["saldo_suficiente"] is False
    )

    print(
        f"{'OK' if ok_0110 else 'FALHOU'} "
        f"| Pedido 0110 "
        f"| Valor: R$ {calculo_0110['valor_total']:.2f} "
        f"| Saldo: R$ "
        f"{orcamento_0110.get('saldo_disponivel', 0):.2f} "
        f"| Suficiente: "
        f"{orcamento_0110.get('saldo_suficiente')}"
    )

valor_invalido = consultar_saldo("205507", -100)

ok_invalido = "erro" in valor_invalido

print(
    f"{'OK' if ok_invalido else 'FALHOU'} "
    "| Valor negativo rejeitado"
)

total_orcamento = int(ok_0110) + int(ok_invalido)

print("=" * 55)
print(f"RESULTADO ORCAMENTO: {total_orcamento}/2")
print("Nenhuma chamada a API realizada.")


def verificar_casos_do_acervo():
    import json

    pedidos = {
        p["numero"]: p for p in json.loads((BASE_DIR / "dados" / "pedidos.json").read_text(encoding="utf-8-sig"))
    }

    def calcular(pedido):
        return calcular_diarias(
            pedido["matricula"], pedido["destino_uf"], pedido["data_partida"], pedido["data_retorno"],
            pedido["data_partida"][:7], data_pedido=pedido["data_pedido"],
        )

    original = pedidos["DIA-2026-0112"]
    cadastro = consultar_servidor(original["matricula"])
    divergente = cadastro.get("encontrado") is True and cadastro.get("nome") != original["nome"]
    vencido = pedidos["DIA-2026-0108"]
    historico = consultar_historico(vencido["matricula"], vencido["data_partida"][:7])
    quantidade = calcular(pedidos["DIA-2026-0103"]).get("quantidade_diarias")
    pedido_saldo = pedidos["DIA-2026-0110"]
    valor = calcular(pedido_saldo).get("valor_total")
    saldo = consultar_saldo(pedido_saldo["matricula"], valor) if valor is not None else {}
    casos = [
        ("0112", divergente, "Matrícula original pertence a cadastro divergente."),
        ("0108", historico.get("possui_prestacao_vencida") is True, "Prestação de contas vencida."),
        ("0103", quantidade == 0.5, f"Quantidade calculada: {quantidade}."),
        ("0110", saldo.get("saldo_suficiente") is False,
         f"Valor pedido: {valor}; saldo disponível: {saldo.get('saldo_disponivel')}."),
    ]
    for protocolo, passou, detalhe in casos:
        print(f"{'OK' if passou else 'FALHOU'} | {protocolo} | {detalhe}")
    return sum(passou for _, passou, _ in casos)


print("\n=== CASOS DO ACERVO OFICIAL ===")
aprovados_acervo = verificar_casos_do_acervo()
print(f"RESULTADO ACERVO: {aprovados_acervo}/4")
if (aprovados, aprovados_historico, total, total_orcamento, aprovados_acervo) != (4, 3, 2, 2, 4):
    raise SystemExit(1)
