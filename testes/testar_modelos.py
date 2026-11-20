from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from pydantic import ValidationError
from modelos import Instrucao

criterios = [
    "cadastro",
    "dados_completos",
    "antecedencia",
    "prestacao_contas",
    "limite_mensal",
    "saldo_orcamentario",
]

exemplo = {
    "numero_pedido": "DIA-TESTE-0001",
    "matricula": "123456",
    "quantidade_diarias": 0.5,
    "valor_total": 110.0,
    "verificacoes": [
        {
            "criterio": criterio,
            "situacao": "atende",
            "detalhe": "Verificacao simulada."
        }
        for criterio in criterios
    ],
    "recomendacao": "apto_para_autorizacao",
    "exige_autorizacao_superior": False,
    "pendencias": [],
    "alertas": [],
    "minuta_despacho": "Encaminhar para revisao humana."
}

aprovados = 0


def testar(nome, dados, deve_aceitar):
    global aprovados

    try:
        Instrucao.model_validate(dados)
        aceito = True
    except ValidationError:
        aceito = False

    passou = aceito == deve_aceitar
    aprovados += int(passou)

    print(f"{'OK' if passou else 'FALHOU'} | {nome}")


testar("Estrutura valida", exemplo, True)

sem_verificacao = {
    **exemplo,
    "verificacoes": exemplo["verificacoes"][:-1]
}
testar("Verificacao ausente rejeitada", sem_verificacao, False)

repetida = {
    **exemplo,
    "verificacoes": (
        exemplo["verificacoes"][:-1]
        + [exemplo["verificacoes"][0]]
    )
}
testar("Verificacao duplicada rejeitada", repetida, False)

recomendacao_invalida = {
    **exemplo,
    "recomendacao": "autorizado"
}
testar("Recomendacao invalida rejeitada", recomendacao_invalida, False)

valor_negativo = {
    **exemplo,
    "valor_total": -100.0
}
testar("Valor negativo rejeitado", valor_negativo, False)

campo_extra = {
    **exemplo,
    "autorizacao_automatica": True
}
testar("Campo extra rejeitado", campo_extra, False)

print("=" * 60)
print(f"RESULTADO: {aprovados}/6 testes aprovados")
print("Nenhuma chamada a API realizada.")
