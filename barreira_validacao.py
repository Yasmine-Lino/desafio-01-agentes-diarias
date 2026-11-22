import re
from decimal import Decimal

from modelos import Instrucao, Verificacao
from seguranca import sanitizar_texto
from validacao_normativa import CRITERIOS, conferir_verificacoes, obter_evidencias_normativas
from validacao_pedido import validar_pedido
from validacao_recomendacao import IMPEDIMENTOS_OBJETIVOS, identificar_urgencia_legitima


CONSULTAS_AGNO = {
    "verificar_cadastro": "consultar_servidor",
    "verificar_prestacoes": "consultar_historico",
    "verificar_calculo": "calcular_diarias",
    "verificar_orcamento": "consultar_saldo",
}
CALCULO_INTERNO = ("verificar_orcamento", "calcular_diarias")
CAMPOS_MONETARIOS = {
    "valor_unitario", "valor_total", "valor_solicitado",
    "saldo_disponivel", "saldo_apos_solicitacao",
}


def _resultado(pedido, erros, *, preliminar=False, instrucao_conferida=None):
    aprovado = not erros
    if not aprovado:
        mensagem = "Instrucao bloqueada para analise manual."
    elif preliminar:
        mensagem = "Evidencia da diligencia preliminar validada."
    else:
        mensagem = "Evidencia deterministica validada."
    return {
        "numero_pedido": str(pedido.get("numero", "")),
        "aprovado": aprovado,
        "texto_conferido": aprovado and instrucao_conferida is not None,
        "instrucao_conferida": instrucao_conferida.model_dump(mode="json")
        if aprovado and instrucao_conferida is not None else None,
        "erros": erros,
        "mensagem": mensagem,
    }


def _mesmo_valor(campo, recebido, esperado):
    if campo in CAMPOS_MONETARIOS:
        if type(recebido) not in (int, float) or type(esperado) not in (int, float):
            return False
        valores = [Decimal(str(valor)) for valor in (recebido, esperado)]
        if not all(valor.is_finite() for valor in valores):
            return False
        recebido_decimal, esperado_decimal = valores
        numerador, denominador = recebido_decimal.as_integer_ratio()
        return numerador * 100 % denominador == 0 and recebido_decimal == esperado_decimal
    if type(esperado) is float:
        return type(recebido) in (int, float) and recebido == esperado
    return type(recebido) is type(esperado) and recebido == esperado


def _mesmos_campos(recebidos, esperados):
    return (
        isinstance(recebidos, dict)
        and recebidos.keys() == esperados.keys()
        and all(_mesmo_valor(campo, recebidos[campo], esperado)
                for campo, esperado in esperados.items())
    )


def _contexto_valido(auditoria, esperado):
    contexto = auditoria.get("contexto_execucao")
    if auditoria.get("estado_contexto") != "completo" or not isinstance(contexto, dict):
        return False
    run_id = contexto.get("run_id")
    return (
        isinstance(run_id, str)
        and re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", run_id) is not None
        and _mesmos_campos(contexto, {"run_id": run_id, **esperado})
    )


def _trilha_validada(auditoria, evidencias):
    if auditoria.get("estado_trilha") != "completa":
        return "Trilha de ferramentas ausente ou incompleta."

    chamadas_agno = auditoria.get("chamadas")
    chamadas_python = auditoria.get("chamadas_python")
    if (
        not isinstance(chamadas_agno, list) or len(chamadas_agno) != len(CONSULTAS_AGNO)
        or not isinstance(chamadas_python, list) or len(chamadas_python) != len(CONSULTAS_AGNO) + 1
        or not all(isinstance(chamada, dict) for chamada in chamadas_agno + chamadas_python)
    ):
        return "Ferramentas ausentes, adicionais ou registros malformados."

    nomes = [chamada.get("nome") for chamada in chamadas_agno]
    if (
        not all(isinstance(nome, str) and nome in CONSULTAS_AGNO for nome in nomes)
        or len(set(nomes)) != len(CONSULTAS_AGNO)
        or not _mesmo_valor("total_chamadas", auditoria.get("total_chamadas"), len(nomes))
        or auditoria.get("nomes_ferramentas") != nomes
    ):
        return "Ferramentas Agno desconhecidas, ausentes ou repetidas."
    ids = [chamada.get("tool_call_id") for chamada in chamadas_agno]
    if (
        not all(isinstance(id_chamada, str)
                and re.fullmatch(r"(?:call|fc)_[A-Za-z0-9_-]{1,128}", id_chamada)
                for id_chamada in ids)
        or len(set(ids)) != len(ids)
    ):
        return "Identificadores das chamadas Agno ausentes ou ambiguos."

    pares = [(nome, consulta) for nome, consulta in CONSULTAS_AGNO.items()]
    pares.append(CALCULO_INTERNO)
    posicoes = {}
    for indice, chamada in enumerate(chamadas_python):
        par = (chamada.get("ferramenta_agno"), chamada.get("nome"))
        if par not in pares or par in posicoes:
            return "Registro Python adicional, desconhecido ou repetido."
        posicoes[par] = indice
        consulta = par[1]
        inicio_esperado = consulta != "consultar_saldo"
        if (
            chamada.get("inicio_chamada") is not inicio_esperado
            or chamada.get("executada") is not True
            or chamada.get("erro") is not False
        ):
            return "Consulta Python nao executada ou registrada com erro."

        argumentos = evidencias["argumentos"][consulta]
        estados = chamada.get("estados_argumentos")
        if (
            not isinstance(estados, dict) or estados.keys() != argumentos.keys()
            or any(estado not in ("presente", "normalizado") for estado in estados.values())
            or not _mesmos_campos(chamada.get("argumentos"), argumentos)
        ):
            return "Argumentos efetivos ausentes, invalidos ou divergentes."
        if not _mesmos_campos(chamada.get("resultado"), evidencias["resultados"][consulta]):
            return "Resultado de consulta Python divergente da evidencia oficial."

    if posicoes[CALCULO_INTERNO] + 1 != posicoes[("verificar_orcamento", "consultar_saldo")]:
        return "Calculo interno e consulta de saldo sem encadeamento verificavel."

    for chamada in chamadas_agno:
        consulta = CONSULTAS_AGNO[chamada["nome"]]
        if (
            chamada.get("erro") is not False
            or not _mesmos_campos(chamada.get("argumentos"), evidencias["argumentos"][consulta])
            or not _mesmos_campos(chamada.get("resultado"), evidencias["resultados"][consulta])
        ):
            return "Registro Agno diverge da consulta Python correspondente."
    return None


def _conferir_identidade(pedido, instrucao):
    erros = []
    if instrucao.numero_pedido != str(pedido.get("numero", "")):
        erros.append("Numero do pedido divergente.")
    if instrucao.matricula.strip() != str(pedido.get("matricula", "")).strip():
        erros.append("Matricula divergente.")
    return erros


def _encaminhamento(pedido, evidencias):
    if not evidencias["analise_merito_permitida"]:
        return "diligencia", False
    situacoes = evidencias["situacoes"]
    if any(situacoes[criterio] == "nao_atende" for criterio in IMPEDIMENTOS_OBJETIVOS):
        return "nao_recomendado", False
    if situacoes["antecedencia"] == "nao_atende":
        if identificar_urgencia_legitima(pedido):
            return "diligencia", True
        return "nao_recomendado", False
    return "apto_para_autorizacao", False


def _conferir_norma(pedido, instrucao, evidencias, encaminhamento):
    erros = []
    conferencia = conferir_verificacoes(pedido, instrucao, evidencias=evidencias)
    for divergencia in conferencia["divergencias"]:
        erros.append("Situacao normativa divergente em " + divergencia["criterio"] + ".")
    recomendacao, exige_superior = encaminhamento
    if instrucao.recomendacao != recomendacao:
        erros.append("Recomendacao divergente da evidencia normativa.")
    if instrucao.exige_autorizacao_superior is not exige_superior:
        erros.append("Indicacao de autorizacao superior divergente.")
    if not evidencias["analise_merito_permitida"] and (
        instrucao.quantidade_diarias is not None or instrucao.valor_total is not None
    ):
        erros.append("Diligencia preliminar nao admite calculo conclusivo.")
    return erros


def _reais(valor):
    return f"R$ {valor:.2f}".replace(".", ",")


def _fundamentos_merito(evidencias):
    contexto = evidencias["contexto"]
    resultados = evidencias["resultados"]
    cadastro = resultados["consultar_servidor"]
    historico = resultados["consultar_historico"]
    calculo = resultados["calcular_diarias"]
    saldo = resultados["consultar_saldo"]
    prestacao = (
        "Há prestação de contas vencida."
        if historico["possui_prestacao_vencida"]
        else "A consulta não identificou prestação de contas vencida."
    )
    suficiencia = "suficiente" if saldo["saldo_suficiente"] else "insuficiente"
    dias = calculo["antecedencia_dias"]
    unidade_prazo = "dia corrido" if dias == 1 else "dias corridos"
    return {
        "cadastro": f"Cadastro compatível com o pedido. Unidade de lotação: {cadastro['unidade']}.",
        "dados_completos": "Os campos obrigatórios do pedido estão preenchidos.",
        "antecedencia": (
            f"{dias} {unidade_prazo} entre o protocolo de "
            f"{contexto['data_pedido']} e a partida de {contexto['data_partida']}. "
            f"O mínimo ordinário é de {evidencias['antecedencia_minima_dias']} dias."
        ),
        "prestacao_contas": f"Data de análise: {contexto['data_analise']}. {prestacao}",
        "limite_mensal": (
            f"Mês da partida: {historico['mes_referencia']}. "
            f"{historico['total_diarias_mes']:g} diárias já concedidas, "
            f"{calculo['total_projetado_mes']:g} projetadas e "
            f"limite de {calculo['limite_mensal']:g} diárias."
        ),
        "saldo_orcamentario": (
            f"Saldo da unidade {saldo['unidade']}: {_reais(saldo['saldo_disponivel'])}, "
            f"{suficiencia} para o valor consultado de {_reais(saldo['valor_solicitado'])}."
        ),
    }


def _produzir_instrucao(pedido, evidencias, encaminhamento):
    protocolo = pedido.get("numero")
    matricula = str(pedido.get("matricula", "")).strip()
    if (
        not isinstance(protocolo, str)
        or re.fullmatch(r"DIA-[0-9]{4}-[0-9]{4}", protocolo) is None
        or re.fullmatch(r"[0-9]{6}", matricula) is None
    ):
        raise ValueError("Identificacao invalida para instrucao conferida.")

    recomendacao, exige_superior = encaminhamento
    situacoes = evidencias["situacoes"]
    pendencias = list(evidencias["pendencias"])
    quantidade = valor = None
    alertas = []
    if not evidencias["analise_merito_permitida"]:
        fundamentos = dict.fromkeys(
            situacoes, "Verificação de mérito suspensa até o saneamento do pedido."
        )
        fundamentos["cadastro"] = "Resultado da validação cadastral preliminar do pedido."
        fundamentos["dados_completos"] = "As pendências da validação preliminar constam nesta instrução."
        alertas.append("A análise de mérito ainda não foi realizada.")
        encaminhar = (
            "Restituam-se os autos para complementar o pedido: "
            + "; ".join(pendencias).rstrip(".")
            + ". Após o saneamento, retome-se a análise."
        )
    else:
        fundamentos = _fundamentos_merito(evidencias)
        calculo = evidencias["resultados"]["calcular_diarias"]
        if exige_superior:
            pendencias.append("Juntar autorização expressa e escrita do Secretário Adjunto ao processo.")
            alertas.append("O relato indica urgência. A autorização escrita não foi comprovada.")
            encaminhar = "Retornem os autos em diligência para comprovação da autorização escrita."
        else:
            quantidade = calculo["quantidade_diarias"]
            valor = calculo["valor_total"]
            impedimentos = [
                fundamentos[criterio] for criterio in CRITERIOS
                if situacoes[criterio] == "nao_atende"
            ]
            if impedimentos:
                alertas.extend(impedimentos)
                encaminhar = (
                    "Recomenda-se não autorizar neste estado. "
                    + " ".join(impedimentos)
                    + " Submetam-se os autos à revisão humana."
                )
            else:
                quantidade_formatada = f"{quantidade:g}".replace(".", ",")
                encaminhar = (
                    f"Recomenda-se encaminhar para conferência {quantidade_formatada} diárias, "
                    f"no valor total de {_reais(valor)}."
                )
        if situacoes["antecedencia"] == "nao_atende":
            alertas.append("Autorização verbal não supre a autorização expressa e escrita.")

    justificativa = str(pedido.get("justificativa") or "")
    if sanitizar_texto(justificativa) != justificativa:
        alertas.append("Foram detectados dados sensíveis na justificativa, omitidos nesta instrução.")
    if re.search(r"\bsistema\s+de\s+an[aá]lise\s*:", justificativa, re.IGNORECASE):
        alertas.append("Foi detectado texto dirigido ao sistema de análise na justificativa.")
    alertas.append("O encaminhamento depende de revisão humana. A decisão final cabe ao ordenador de despesa.")

    return Instrucao(
        numero_pedido=protocolo,
        matricula=matricula,
        quantidade_diarias=quantidade,
        valor_total=valor,
        verificacoes=[
            Verificacao(criterio=criterio, situacao=situacoes[criterio], detalhe=fundamentos[criterio])
            for criterio in CRITERIOS
        ],
        recomendacao=recomendacao,
        exige_autorizacao_superior=exige_superior,
        pendencias=pendencias,
        alertas=alertas,
        minuta_despacho=(
            f"Pedido {protocolo}. {encaminhar} "
            "Esta minuta fica sujeita à revisão humana e à decisão do ordenador de despesa."
        ),
    )


def validar_diligencia_preliminar(pedido: dict, instrucao: Instrucao, auditoria: dict) -> dict:
    """Valida o encaminhamento local sem exigir uma execucao Agno."""
    erros = _conferir_identidade(pedido, instrucao)
    if (
        not isinstance(auditoria, dict)
        or auditoria.get("chamadas") != []
        or auditoria.get("chamadas_python", []) != []
        or auditoria.get("estado_trilha") not in (None, "ausente", "vazia")
        or auditoria.get("nomes_ferramentas", []) != []
        or not _mesmo_valor("total_chamadas", auditoria.get("total_chamadas", 0), 0)
    ):
        erros.append("Diligencia preliminar exige ausencia de consultas de merito.")
    try:
        evidencias = obter_evidencias_normativas(pedido)
        if evidencias["analise_merito_permitida"]:
            erros.append("Pedido completo nao pode usar fluxo preliminar.")
        else:
            if not evidencias["pendencias"] or any(
                pendencia not in instrucao.pendencias for pendencia in evidencias["pendencias"]
            ):
                erros.append("Pendencia preliminar obrigatoria ausente.")
            encaminhamento = _encaminhamento(pedido, evidencias)
            erros.extend(_conferir_norma(pedido, instrucao, evidencias, encaminhamento))
            if not erros:
                conferida = _produzir_instrucao(pedido, evidencias, encaminhamento)
                return _resultado(pedido, erros, preliminar=True, instrucao_conferida=conferida)
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError):
        erros.append("Evidencia ou instrucao conferida indisponivel ou invalida.")
    return _resultado(pedido, erros, preliminar=True)


def validar_instrucao(pedido: dict, instrucao: Instrucao, auditoria: dict) -> dict:
    """Valida evidencias estruturadas. A aprovacao nao confere o texto livre."""
    try:
        if not validar_pedido(pedido)["pode_analisar_merito"]:
            return validar_diligencia_preliminar(pedido, instrucao, auditoria)

        erros = _conferir_identidade(pedido, instrucao)
        if not isinstance(auditoria, dict):
            return _resultado(pedido, erros + ["Auditoria da execucao ausente ou invalida."])

        evidencias = obter_evidencias_normativas(pedido)
        esperado = evidencias["contexto"]
        if not _contexto_valido(auditoria, esperado):
            erros.append("Contexto da execucao ausente, invalido ou divergente.")
        erro_trilha = _trilha_validada(auditoria, evidencias)
        if erro_trilha:
            erros.append(erro_trilha)

        encaminhamento = _encaminhamento(pedido, evidencias)
        calculo = evidencias["resultados"]["calcular_diarias"]
        diligencia_sem_totais = (
            encaminhamento[0] == "diligencia"
            and instrucao.quantidade_diarias is None
            and instrucao.valor_total is None
        )
        if not diligencia_sem_totais:
            if not _mesmo_valor(
                "quantidade_diarias", instrucao.quantidade_diarias, calculo["quantidade_diarias"]
            ):
                erros.append("Quantidade de diarias divergente.")
            if not _mesmo_valor("valor_total", instrucao.valor_total, calculo["valor_total"]):
                erros.append("Valor total divergente.")

        erros.extend(_conferir_norma(pedido, instrucao, evidencias, encaminhamento))
        if not erros:
            conferida = _produzir_instrucao(pedido, evidencias, encaminhamento)
            return _resultado(pedido, erros, instrucao_conferida=conferida)
    except (OSError, ValueError, TypeError, KeyError, ArithmeticError):
        return _resultado(pedido, ["Evidencia ou instrucao conferida indisponivel ou invalida."])
    return _resultado(pedido, erros)
