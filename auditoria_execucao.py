import json
from dataclasses import asdict, is_dataclass
from typing import Any

from seguranca import sanitizar_texto


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


def registrar_ferramentas(resposta) -> dict:
    """Extrai ferramentas realmente registradas pelo Agno."""

    registros = []

    for ferramenta in (resposta.tools or []):
        argumentos = sanitizar_objeto(
            ferramenta.tool_args or {}
        )

        resultado = sanitizar_objeto(
            ferramenta.result
        )

        metricas = sanitizar_objeto(
            ferramenta.metrics
        )

        registros.append({
            "tool_call_id": ferramenta.tool_call_id,
            "nome": ferramenta.tool_name,
            "argumentos": argumentos,
            "resultado": resultado,
            "erro": bool(ferramenta.tool_call_error),
            "metricas": metricas,
        })

    return {
        "total_chamadas": len(registros),
        "nomes_ferramentas": [
            registro["nome"]
            for registro in registros
        ],
        "chamadas": registros,
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
