import json
import re
from datetime import date

from ferramentas import (
    DADOS_DIR,
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


CAMPOS_RESULTADO = {
    "consultar_servidor": ("encontrado", "matricula", "unidade"),
    "consultar_historico": (
        "matricula", "mes_referencia", "data_analise",
        "total_diarias_mes", "possui_prestacao_vencida",
    ),
    "calcular_diarias": (
        "matricula", "data_partida", "data_retorno", "quantidade_diarias",
        "valor_unitario", "valor_total", "antecedencia_dias", "antecedencia_atendida",
        "diarias_anteriores_mes", "total_projetado_mes", "limite_mensal", "limite_mensal_atendido",
    ),
    "consultar_saldo": (
        "matricula", "unidade", "saldo_disponivel", "valor_solicitado",
        "saldo_suficiente", "saldo_apos_solicitacao",
    ),
}


def _data_iso(valor):
    if not isinstance(valor, str) or date.fromisoformat(valor).isoformat() != valor:
        raise ValueError("Data operacional invalida.")
    return valor


def _contexto_esperado(pedido, matricula, data_analise):
    protocolo = pedido["numero"]
    municipio = pedido["destino_municipio"]
    destino_uf = pedido["destino_uf"].strip().upper()
    if (
        re.fullmatch(r"DIA-[0-9]{4}-[0-9]{4}", protocolo) is None
        or re.fullmatch(r"[0-9]{6}", matricula) is None
        or re.fullmatch(r"[A-Z]{2}", destino_uf) is None
        or not isinstance(municipio, str)
        or not 1 <= len(municipio) <= 80
        or not any(c.isalpha() for c in municipio)
        or not all(c.isalpha() or c in " -'\u2019." for c in municipio)
    ):
        raise ValueError("Identificacao operacional invalida.")
    return {
        "protocolo": protocolo,
        "session_id": protocolo,
        "matricula": matricula,
        "user_id": matricula,
        "destino_municipio": municipio,
        "destino_uf": destino_uf,
        "data_pedido": _data_iso(pedido["data_pedido"]),
        "data_partida": _data_iso(pedido["data_partida"]),
        "data_retorno": _data_iso(pedido["data_retorno"]),
        "data_analise": _data_iso(data_analise),
    }


def obter_evidencias_normativas(pedido: dict) -> dict:
    """Calcula criterios objetivos usando ferramentas locais."""

    validacao = validar_pedido(pedido)

    matricula = str(pedido.get("matricula", "")).strip()
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

    tabela = json.loads(
        (DADOS_DIR / "tabela_diarias.json").read_text(encoding="utf-8-sig")
    )
    contexto = _contexto_esperado(pedido, matricula, tabela["data_da_analise"])
    argumentos_historico = {
        "matricula": matricula,
        "mes_referencia": partida[:7],
        "data_analise": contexto["data_analise"],
    }
    argumentos_calculo = {
        **argumentos_historico,
        "destino_uf": contexto["destino_uf"],
        "data_pedido": contexto["data_pedido"],
        "data_partida": partida,
        "data_retorno": retorno,
    }
    historico = consultar_historico(**argumentos_historico)
    calculo = calcular_diarias(**argumentos_calculo)

    if "erro" in historico or "erro" in calculo:
        raise ValueError("Falha ao consultar evidencias normativas.")

    grupo = cadastro.get("grupo_diaria")
    if (
        cadastro.get("encontrado") is not True
        or grupo not in tabela["valores"]
        or calculo.get("grupo_diaria") != grupo
        or calculo["valor_unitario"] != tabela["valores"][grupo][calculo["categoria_destino"]]
    ):
        raise ValueError("Cadastro, grupo ou tarifa inconsistente.")

    argumentos_saldo = {
        "matricula": matricula,
        "valor_solicitado": calculo["valor_total"],
    }
    saldo = consultar_saldo(**argumentos_saldo)
    if "erro" in saldo or saldo.get("unidade") != cadastro.get("unidade"):
        raise ValueError("Saldo ou unidade orcamentaria inconsistente.")

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

    fontes = {
        "consultar_servidor": cadastro,
        "consultar_historico": historico,
        "calcular_diarias": calculo,
        "consultar_saldo": saldo,
    }
    return {
        "numero_pedido": pedido.get("numero"),
        "situacoes": situacoes,
        "pendencias": validacao["pendencias"],
        "analise_merito_permitida": True,
        "contexto": contexto,
        "antecedencia_minima_dias": tabela["antecedencia_minima_dias"],
        "argumentos": {
            "consultar_servidor": {"matricula": matricula},
            "consultar_historico": argumentos_historico,
            "calcular_diarias": argumentos_calculo,
            "consultar_saldo": argumentos_saldo,
        },
        "resultados": {
            consulta: {campo: fontes[consulta][campo] for campo in campos}
            for consulta, campos in CAMPOS_RESULTADO.items()
        },
    }


def conferir_verificacoes(pedido: dict, instrucao, *, evidencias=None) -> dict:
    """Compara verificacoes do agente com evidencias oficiais."""

    if evidencias is None:
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
