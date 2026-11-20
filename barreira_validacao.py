from validacao_recomendacao import conferir_recomendacao
from validacao_normativa import conferir_verificacoes
from math import isclose

from ferramentas import calcular_diarias
from modelos import Instrucao


FERRAMENTAS_OBRIGATORIAS = {
    "verificar_cadastro",
    "verificar_prestacoes",
    "verificar_calculo",
    "verificar_orcamento",
}



def validar_diligencia_preliminar(
    pedido: dict,
    instrucao: Instrucao,
    auditoria: dict,
) -> dict:
    """Valida diligencia sem permitir analise de merito."""

    from validacao_pedido import validar_pedido

    erros = []
    validacao = validar_pedido(pedido)

    if validacao["pode_analisar_merito"]:
        erros.append(
            "Pedido completo nao pode usar fluxo preliminar."
        )

    if instrucao.numero_pedido != str(pedido.get("numero", "")):
        erros.append("Numero do pedido divergente.")

    if str(instrucao.matricula) != str(pedido.get("matricula", "")):
        erros.append("Matricula divergente.")

    if instrucao.recomendacao != "diligencia":
        erros.append(
            "Pedido incompleto deve permanecer em diligencia."
        )

    if (
        instrucao.quantidade_diarias is not None
        or instrucao.valor_total is not None
    ):
        erros.append(
            "Diligencia preliminar nao permite calculo conclusivo."
        )

    if instrucao.exige_autorizacao_superior:
        erros.append(
            "Autorizacao superior nao deve ser inferida "
            "antes da analise de merito."
        )

    if auditoria.get("chamadas", []):
        erros.append(
            "Ferramentas do agente nao devem ser executadas "
            "na diligencia preliminar."
        )

    if not instrucao.pendencias:
        erros.append("Diligencia sem pendencias.")

    for pendencia in validacao["pendencias"]:
        if pendencia not in instrucao.pendencias:
            erros.append(
                "Pendencia preliminar ausente: " + pendencia
            )

    conferencia_normativa = conferir_verificacoes(
        pedido,
        instrucao,
    )

    if not conferencia_normativa["aprovado"]:
        for divergencia in conferencia_normativa["divergencias"]:
            erros.append(
                "Divergencia normativa em "
                + divergencia["criterio"]
                + ": esperado="
                + str(divergencia["esperado"])
                + ", recebido="
                + str(divergencia["recebido"])
            )

    conferencia_recomendacao = conferir_recomendacao(
        pedido,
        instrucao,
    )

    if not conferencia_recomendacao["aprovado"]:
        erros.extend(conferencia_recomendacao["erros"])

    return {
        "numero_pedido": str(pedido.get("numero", "")),
        "aprovado": len(erros) == 0,
        "erros": erros,
        "mensagem": (
            "Diligencia preliminar validada."
            if not erros
            else "Diligencia preliminar bloqueada."
        ),
    }


def validar_instrucao(
    pedido: dict,
    instrucao: Instrucao,
    auditoria: dict,
) -> dict:
    """Valida a instrucao contra o pedido e as evidencias."""

    from validacao_pedido import validar_pedido

    validacao_preliminar = validar_pedido(pedido)

    if not validacao_preliminar["pode_analisar_merito"]:
        return validar_diligencia_preliminar(
            pedido,
            instrucao,
            auditoria,
        )

    erros = []

    numero = str(pedido.get("numero", ""))
    matricula = str(pedido.get("matricula", ""))

    if instrucao.numero_pedido != numero:
        erros.append("Numero do pedido divergente.")

    if str(instrucao.matricula) != matricula:
        erros.append("Matricula divergente.")

    chamadas = auditoria.get("chamadas", [])

    nomes = {
        chamada.get("nome")
        for chamada in chamadas
    }

    ausentes = FERRAMENTAS_OBRIGATORIAS - nomes

    if ausentes:
        erros.append(
            "Ferramentas obrigatorias nao executadas: "
            + ", ".join(sorted(ausentes))
        )

    for chamada in chamadas:
        if chamada.get("erro"):
            erros.append(
                "Erro na ferramenta: "
                + str(chamada.get("nome"))
            )

        argumentos = chamada.get("argumentos") or {}

        if not isinstance(argumentos, dict):
            erros.append("Argumentos de ferramenta invalidos.")
            continue

        if "matricula" in argumentos:
            if str(argumentos["matricula"]) != matricula:
                erros.append(
                    "Matricula divergente nos argumentos."
                )

        for campo in ["data_partida", "data_retorno"]:
            if campo in argumentos:
                if str(argumentos[campo]) != str(
                    pedido.get(campo)
                ):
                    erros.append(
                        f"Data divergente nos argumentos: {campo}."
                    )

    partida = pedido.get("data_partida")
    retorno = pedido.get("data_retorno")

    if not partida or not retorno:
        erros.append("Datas obrigatorias ausentes.")
    else:
        calculo = calcular_diarias(
            matricula,
            pedido["destino_uf"],
            partida,
            retorno,
            str(partida)[:7],
        )

        if "erro" in calculo:
            erros.append("Falha no calculo oficial.")
        else:
            quantidade = instrucao.quantidade_diarias
            valor = instrucao.valor_total

            if quantidade is None or not isclose(
                quantidade,
                calculo["quantidade_diarias"],
                abs_tol=0.001,
            ):
                erros.append(
                    "Quantidade de diarias divergente."
                )

            if valor is None or not isclose(
                valor,
                calculo["valor_total"],
                abs_tol=0.01,
            ):
                erros.append(
                    "Valor total divergente."
                )

    conferencia_normativa = conferir_verificacoes(
        pedido,
        instrucao,
    )

    if not conferencia_normativa["aprovado"]:
        for divergencia in conferencia_normativa["divergencias"]:
            erros.append(
                "Divergencia normativa em "
                + divergencia["criterio"]
                + ": esperado="
                + str(divergencia["esperado"])
                + ", recebido="
                + str(divergencia["recebido"])
            )

    conferencia_recomendacao = conferir_recomendacao(
        pedido,
        instrucao,
    )

    if not conferencia_recomendacao["aprovado"]:
        erros.extend(conferencia_recomendacao["erros"])

    return {
        "numero_pedido": numero,
        "aprovado": len(erros) == 0,
        "erros": erros,
        "mensagem": (
            "Instrucao validada."
            if not erros
            else "Instrucao bloqueada para revisao humana."
        ),
    }
