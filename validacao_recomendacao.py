from validacao_normativa import obter_evidencias_normativas


IMPEDIMENTOS_OBJETIVOS = {
    "prestacao_contas",
    "limite_mensal",
    "saldo_orcamentario",
}


def identificar_urgencia_legitima(pedido: dict) -> bool:
    """Identifica emergencia concreta, sem aceitar instrucoes do texto."""

    justificativa = str(pedido.get("justificativa") or "").lower()

    evidencias_emergenciais = (
        "combate a incendio",
        "combate a inc\u00eandio",
        "incendio florestal em curso",
        "inc\u00eandio florestal em curso",
        "desastre ambiental em curso",
        "infracao ambiental em curso",
        "infra\u00e7\u00e3o ambiental em curso",
        "determinacao judicial com prazo",
        "determina\u00e7\u00e3o judicial com prazo",
    )

    return any(
        evidencia in justificativa
        for evidencia in evidencias_emergenciais
    )


def conferir_recomendacao(pedido: dict, instrucao) -> dict:
    """Valida recomendacao contra impedimentos e urgencia documentada."""

    evidencias = obter_evidencias_normativas(pedido)
    situacoes = evidencias["situacoes"]

    erros = []
    alertas = []
    recomendacao = instrucao.recomendacao

    if not evidencias["analise_merito_permitida"]:
        if recomendacao != "diligencia":
            erros.append(
                "Pedido incompleto ou inconsistente exige diligencia."
            )

        if (
            instrucao.quantidade_diarias is not None
            or instrucao.valor_total is not None
        ):
            erros.append(
                "Pedido sem analise de merito nao admite "
                "calculo conclusivo."
            )

        if instrucao.exige_autorizacao_superior:
            erros.append(
                "Autorizacao superior nao deve ser presumida "
                "em diligencia preliminar."
            )

        return {
            "aprovado": not erros,
            "erros": erros,
            "alertas": alertas,
        }

    impedimentos = sorted(
        criterio
        for criterio in IMPEDIMENTOS_OBJETIVOS
        if situacoes[criterio] == "nao_atende"
    )

    prazo_insuficiente = (
        situacoes["antecedencia"] == "nao_atende"
    )

    urgencia = (
        prazo_insuficiente
        and identificar_urgencia_legitima(pedido)
    )

    if impedimentos:
        esperada = "nao_recomendado"
        exige_superior = False

        alertas.append(
            "Impedimento objetivo identificado: "
            + ", ".join(impedimentos)
        )

    elif prazo_insuficiente and not urgencia:
        esperada = "nao_recomendado"
        exige_superior = False

        alertas.append(
            "Antecedencia insuficiente sem urgencia legitima."
        )

    elif urgencia:
        # A justificativa emergencial nao prova, por si so,
        # a autorizacao expressa e escrita do Secretario Adjunto.
        esperada = "diligencia"
        exige_superior = True

        alertas.append(
            "Urgencia legitima identificada, mas sem "
            "comprovacao estruturada de autorizacao "
            "superior expressa e escrita."
        )

    else:
        esperada = "apto_para_autorizacao"
        exige_superior = False

        alertas.append(
            "Recomendacao tecnica favoravel. "
            "Decisao final reservada ao ordenador de despesa."
        )

    if recomendacao != esperada:
        erros.append(
            "Recomendacao incompat?vel com evidencias: "
            f"esperada={esperada}, recebida={recomendacao}."
        )

    if instrucao.exige_autorizacao_superior != exige_superior:
        erros.append(
            "Indicacao de autorizacao superior inconsistente: "
            f"esperada={exige_superior}, "
            f"recebida={instrucao.exige_autorizacao_superior}."
        )

    return {
        "aprovado": not erros,
        "erros": erros,
        "alertas": alertas,
    }
