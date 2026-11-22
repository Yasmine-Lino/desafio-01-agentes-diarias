import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from seguranca import sanitizar_texto, criar_guardrail_pii

# Marcadores sinteticos para testar a mascara, inclusive CPF invalido.

testes = [
    (
        "CPF formatado",
        "Meu CPF e 000.000.000-00",
        "000.000.000-00"
    ),
    (
        "CPF sem pontuacao",
        "CPF 00000000000",
        "00000000000"
    ),
    (
        "Conta bancaria",
        "Minha conta corrente: 00000-0",
        "00000-0"
    ),
    (
        "Agencia bancaria",
        "Agencia: 0000",
        "0000"
    ),
    (
        "Email",
        "Contato: teste@example.invalid",
        "teste@example.invalid"
    ),
]

aprovados = 0

for nome, entrada, segredo in testes:
    saida = sanitizar_texto(entrada)
    passou = segredo not in saida

    aprovados += int(passou)

    print(
        f"{'OK' if passou else 'FALHOU'} "
        f"| {nome}"
    )

guardrail = criar_guardrail_pii()
passou = guardrail is not None
aprovados += int(passou)

print(
    f"{'OK' if passou else 'FALHOU'} "
    "| Guardrail Agno instanciado"
)

print("=" * 60)
print(f"RESULTADO: {aprovados}/6 testes aprovados")
print("Nenhuma chamada a API realizada.")

if aprovados != 6:
    raise SystemExit(1)
