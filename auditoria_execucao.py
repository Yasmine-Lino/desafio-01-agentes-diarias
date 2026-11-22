
import re
from collections import Counter
from contextvars import ContextVar
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date
from math import isfinite
from typing import Any

from seguranca import sanitizar_texto


TRILHA_FERRAMENTAS: ContextVar[list[dict] | None] = ContextVar(
    "trilha_ferramentas", default=None
)

_FORMATOS = {
    "matricula": r"[0-9]{6}",
    "destino_uf": r"[A-Z]{2}",
    "data_pedido": r"[0-9]{4}-[0-9]{2}-[0-9]{2}",
    "data_partida": r"[0-9]{4}-[0-9]{2}-[0-9]{2}",
    "data_retorno": r"[0-9]{4}-[0-9]{2}-[0-9]{2}",
    "data_analise": r"[0-9]{4}-[0-9]{2}-[0-9]{2}",
    "mes_referencia": r"[0-9]{4}-[0-9]{2}",
    "unidade": r"[A-Z]{2,5}",
}
_CONSULTAS = {
    "consultar_servidor": (
        ("matricula",),
        ("encontrado", "matricula", "unidade"),
    ),
    "consultar_historico": (
        ("matricula", "mes_referencia", "data_analise"),
        ("matricula", "mes_referencia", "data_analise", "total_diarias_mes",
         "possui_prestacao_vencida"),
    ),
    "calcular_diarias": (
        ("matricula", "destino_uf", "data_pedido", "data_partida", "data_retorno",
         "mes_referencia", "data_analise"),
        ("matricula", "data_partida", "data_retorno", "quantidade_diarias",
         "valor_unitario", "valor_total", "antecedencia_dias",
         "antecedencia_atendida", "diarias_anteriores_mes", "total_projetado_mes",
         "limite_mensal", "limite_mensal_atendido"),
    ),
    "consultar_saldo": (
        ("matricula", "valor_solicitado"),
        ("matricula", "unidade", "saldo_disponivel", "valor_solicitado",
         "saldo_suficiente", "saldo_apos_solicitacao"),
    ),
}
_FERRAMENTAS = {
    "verificar_cadastro": "consultar_servidor",
    "verificar_prestacoes": "consultar_historico",
    "verificar_calculo": "calcular_diarias",
    "verificar_orcamento": "consultar_saldo",
}
_METRICAS = ("time", "duration", "duration_seconds")


def _numero_finito(valor):
    return type(valor) is int or (type(valor) is float and isfinite(valor))


def _valor_operacional(campo, valor):
    if campo in _FORMATOS:
        return isinstance(valor, str) and re.fullmatch(_FORMATOS[campo], valor) is not None
    return type(valor) is bool or _numero_finito(valor)


def _argumento_efetivo(campo, valor):
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None, "ausente"

    efetivo = valor
    if isinstance(valor, str):
        if campo == "matricula":
            efetivo = valor.strip()
        elif campo == "destino_uf":
            efetivo = valor.strip().upper()

    if campo == "valor_solicitado":
        valido = _numero_finito(efetivo)
    else:
        valido = _valor_operacional(campo, efetivo)
        if valido and campo.startswith("data_"):
            try:
                date.fromisoformat(efetivo)
            except ValueError:
                valido = False
        if valido and campo == "mes_referencia":
            valido = 1 <= int(efetivo[5:]) <= 12

    if not valido:
        return None, "invalido"
    return efetivo, "normalizado" if efetivo != valor else "presente"


def executar_consulta_auditada(
    chave, funcao, /, *, ferramenta_agno, inicio_chamada=True, **argumentos
):
    """Registra a tentativa e passa ? fun??o os mesmos argumentos efetivos."""
    campos_entrada, campos_saida = _CONSULTAS[chave]
    efetivos = {}
    estados = {}
    for campo in campos_entrada:
        valor, estado = _argumento_efetivo(campo, argumentos.get(campo))
        estados[campo] = estado
        if estado in ("presente", "normalizado"):
            efetivos[campo] = valor

    registro = {
        "nome": chave,
        "ferramenta_agno": ferramenta_agno,
        "inicio_chamada": inicio_chamada,
        "argumentos": {},
        "estados_argumentos": estados,
        "executada": False,
        "resultado": {},
        "erro": True,
    }
    trilha = TRILHA_FERRAMENTAS.get()
    if trilha is not None:
        trilha.append(registro)

    if efetivos.keys() != estados.keys() or argumentos.keys() - estados.keys():
        return {"erro": "Argumentos da consulta ausentes ou invalidos."}

    registro["argumentos"] = efetivos
    registro["executada"] = True
    resultado = funcao(**efetivos)
    if isinstance(resultado, dict):
        registro["resultado"] = {
            campo: resultado[campo]
            for campo in campos_saida
            if _valor_operacional(campo, resultado.get(campo))
        }
        registro["erro"] = "erro" in resultado
    return resultado


def sanitizar_objeto(valor: Any) -> Any:
    """Remove dados pessoais de estruturas destinadas aos registros."""

    if isinstance(valor, str):
        return sanitizar_texto(valor)

    if isinstance(valor, dict):
        return {
            str(chave): sanitizar_objeto(conteudo)
            for chave, conteudo in valor.items()
        }

    if isinstance(valor, (list, tuple)):
        return [sanitizar_objeto(item) for item in valor]

    if is_dataclass(valor) and not isinstance(valor, type):
        return sanitizar_objeto(asdict(valor))

    if isinstance(valor, (int, float, bool)) or valor is None:
        return valor

    return sanitizar_texto(str(valor))


@dataclass(frozen=True, slots=True)
class ContextoExecucao:
    run_id: str
    protocolo: str
    matricula: str
    destino_municipio: str
    destino_uf: str
    data_pedido: str
    data_partida: str
    data_retorno: str
    data_analise: str
    entrada_conferida: bool


def _contexto_publico(resposta, chamadas_python):
    contexto = getattr(resposta, "_contexto_execucao", None)
    if contexto is None:
        return "ausente", None
    if not isinstance(contexto, ContextoExecucao):
        return "inconsistente", None

    if (
        contexto.entrada_conferida is not True
        or contexto.run_id != resposta.run_id
        or contexto.protocolo != resposta.session_id
        or contexto.matricula != resposta.user_id
        or not isinstance(contexto.run_id, str)
        or not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", contexto.run_id)
        or not isinstance(contexto.protocolo, str)
        or not re.fullmatch(r"DIA-[0-9]{4}-[0-9]{4}", contexto.protocolo)
        or not _valor_operacional("matricula", contexto.matricula)
        or not _valor_operacional("destino_uf", contexto.destino_uf)
    ):
        return "inconsistente", None

    municipio = contexto.destino_municipio
    if (
        not isinstance(municipio, str)
        or not 1 <= len(municipio) <= 80
        or not any(caractere.isalpha() for caractere in municipio)
        or not all(caractere.isalpha() or caractere in " -'\u2019." for caractere in municipio)
    ):
        return "inconsistente", None

    datas = {
        "data_pedido": contexto.data_pedido,
        "data_partida": contexto.data_partida,
        "data_retorno": contexto.data_retorno,
        "data_analise": contexto.data_analise,
    }
    if any(
        _argumento_efetivo("data_analise", valor)[1] != "presente"
        for valor in datas.values()
    ):
        return "inconsistente", None

    if any(
        chamada["executada"] is True
        and chamada["nome"] in ("consultar_historico", "calcular_diarias")
        and chamada["argumentos"].get("data_analise") != contexto.data_analise
        for chamada in chamadas_python
    ):
        return "inconsistente", None

    return "completo", {
        "run_id": contexto.run_id,
        "protocolo": contexto.protocolo,
        "session_id": contexto.protocolo,
        "matricula": contexto.matricula,
        "user_id": contexto.matricula,
        "destino_municipio": municipio,
        "destino_uf": contexto.destino_uf,
        **datas,
    }


def registrar_ferramentas(resposta) -> dict:
    """Publica uma auditoria minimizada, independente do conte?do do modelo."""
    trilha = getattr(resposta, "_trilha_ferramentas", None)
    chamadas_python = [
        {
            **registro,
            "argumentos": dict(registro["argumentos"]),
            "estados_argumentos": dict(registro["estados_argumentos"]),
            "resultado": dict(registro["resultado"]),
        }
        for registro in (trilha or ())
    ]
    chamadas_agno = resposta.tools or []
    contagem_agno = Counter(
        chamada.tool_name if chamada.tool_name in _FERRAMENTAS else None
        for chamada in chamadas_agno
    )
    contagem_python = Counter(
        chamada["ferramenta_agno"]
        for chamada in chamadas_python if chamada["inicio_chamada"]
    )

    registros = []
    for ferramenta in chamadas_agno:
        nome = ferramenta.tool_name if ferramenta.tool_name in _FERRAMENTAS else None
        candidatos = [
            chamada for chamada in chamadas_python
            if chamada["ferramenta_agno"] == nome
            and chamada["nome"] == _FERRAMENTAS.get(nome)
        ]
        evidencia = {}
        if nome and contagem_agno[nome] == contagem_python[nome] == len(candidatos) == 1:
            evidencia = candidatos[0]

        identificador = ferramenta.tool_call_id
        metricas = ferramenta.metrics
        registros.append({
            "tool_call_id": identificador if isinstance(identificador, str)
            and re.fullmatch(r"(?:call|fc)_[A-Za-z0-9_-]{1,128}", identificador)
            else None,
            "nome": nome,
            "argumentos": dict(evidencia.get("argumentos", {})),
            "resultado": dict(evidencia.get("resultado", {})),
            "erro": bool(ferramenta.tool_call_error) or evidencia.get("erro", False),
            "metricas": {
                campo: valor for campo in _METRICAS
                if _numero_finito(valor := (
                    metricas.get(campo) if isinstance(metricas, dict)
                    else getattr(metricas, campo, None)
                ))
            },
        })

    if trilha is None:
        estado_trilha = "ausente"
    elif contagem_agno != contagem_python:
        estado_trilha = "incompleta"
    elif not chamadas_python:
        estado_trilha = "vazia"
    else:
        estado_trilha = "completa"

    estado_contexto, contexto_execucao = _contexto_publico(resposta, chamadas_python)
    return {
        "total_chamadas": len(registros),
        "nomes_ferramentas": [registro["nome"] for registro in registros],
        "chamadas": registros,
        "chamadas_python": chamadas_python,
        "estado_trilha": estado_trilha,
        "estado_contexto": estado_contexto,
        "contexto_execucao": contexto_execucao,
    }


def imprimir_auditoria_ferramentas(auditoria: dict) -> None:
    """Exibe um resumo das chamadas sem imprimir dados sensíveis."""

    print("\n=== AUDITORIA DAS FERRAMENTAS ===")
    print("Total de chamadas:", auditoria["total_chamadas"])

    for indice, registro in enumerate(
        auditoria["chamadas"], start=1
    ):
        print(
            f"{indice}. {registro['nome']} | "
            f"Erro: {registro['erro']}"
        )

    print(
        "Ferramentas distintas:",
        len(set(auditoria["nomes_ferramentas"]))
    )
