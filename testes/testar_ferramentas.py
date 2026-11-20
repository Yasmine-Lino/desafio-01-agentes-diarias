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
    mes_referencia="2026-11"
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
    mes_referencia="2026-10"
)

ok_0105 = teste_0105.get("antecedencia_atendida") is False

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
    mes_referencia="2026-11"
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
