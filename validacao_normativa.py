from ferramentas import (
    consultar_servidor,
    consultar_historico,
    calcular_diarias,
    consultar_saldo,
)
from validacao_pedido import validar_pedido


CRITERIOS = [
    "cadastro",
    "dados_completos",
    "antecedencia",
    "prestacao_contas",
    "limite_mensal",
    "saldo_orcamentario",
]


def obter_evidencias_normativas(pedido: dict) -> dict:
    """Calcula criterios objetivos usando ferramentas locais."""

    validacao = validar_pedido(pedido)

    matricula = str(pedido.get("matricula", ""))
    partida = pedido.get("data_partida")
    retorno = pedido.get("data_retorno")

    cadastro = consultar_servidor(matricula)

    situacoes = {
        "cadastro": (
            "atende"
            if "erro" not in cadastro
            and not any(
                "diverg" in pendencia.lower()
                for pendencia in validacao["pendencias"]
            )
            else "nao_atende"
        ),
        "dados_completos": (
            "atende"
            if all(
                pedido.get(campo) is not None
                and str(pedido.get(campo)).strip()
                for campo in (
                    "numero",
                    "matricula",
                    "nome",
                    "destino_municipio",
                    "destino_uf",
                    "data_partida",
                    "data_retorno",
                    "justificativa",
                )
            )
            else "nao_atende"
        ),
        "antecedencia": "nao_verificado",
        "prestacao_contas": "nao_verificado",
        "limite_mensal": "nao_verificado",
        "saldo_orcamentario": "nao_verificado",
    }

    if not validacao["pode_analisar_merito"]:
        return {
            "numero_pedido": pedido.get("numero"),
            "situacoes": situacoes,
            "pendencias": validacao["pendencias"],
            "analise_merito_permitida": False,
        }

    historico = consultar_historico(
        matricula,
        str(partida)[:7],
        "2026-10-09",
    )

    calculo = calcular_diarias(
        matricula,
        pedido["destino_uf"],
        partida,
        retorno,
        str(partida)[:7],
        "2026-10-09",
    )

    if "erro" in historico or "erro" in calculo:
        raise ValueError(
            "Falha ao consultar evidencias normativas."
        )

    saldo = consultar_saldo(
        matricula,
        calculo["valor_total"],
    )

    if "erro" in saldo:
        raise ValueError(
            "Falha ao consultar saldo orcamentario."
        )

    situacoes["antecedencia"] = (
        "atende"
        if calculo["antecedencia_atendida"]
        else "nao_atende"
    )

    situacoes["prestacao_contas"] = (
        "nao_atende"
        if historico["possui_prestacao_vencida"]
        else "atende"
    )

    situacoes["limite_mensal"] = (
        "atende"
        if calculo["limite_mensal_atendido"]
        else "nao_atende"
    )

    situacoes["saldo_orcamentario"] = (
        "atende"
        if saldo["saldo_suficiente"]
        else "nao_atende"
    )

    return {
        "numero_pedido": pedido.get("numero"),
        "situacoes": situacoes,
        "pendencias": validacao["pendencias"],
        "analise_merito_permitida": True,
    }


def conferir_verificacoes(pedido: dict, instrucao) -> dict:
    """Compara verificacoes do agente com evidencias oficiais."""

    evidencias = obter_evidencias_normativas(pedido)

    recebidas = {
        verificacao.criterio: verificacao.situacao
        for verificacao in instrucao.verificacoes
    }

    divergencias = []

    for criterio in CRITERIOS:
        esperado = evidencias["situacoes"][criterio]
        recebido = recebidas.get(criterio)

        if recebido != esperado:
            divergencias.append({
                "criterio": criterio,
                "esperado": esperado,
                "recebido": recebido,
            })

    return {
        "aprovado": len(divergencias) == 0,
        "divergencias": divergencias,
        "evidencias": evidencias,
    }
