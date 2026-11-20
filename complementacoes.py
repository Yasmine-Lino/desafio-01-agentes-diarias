import json
import re
from copy import deepcopy
from datetime import date
from pathlib import Path

from agente import obter_pedido
from ferramentas import consultar_servidor
from validacao_pedido import validar_pedido


BASE = Path(__file__).resolve().parent
ARQUIVO_COMPLEMENTACOES = BASE / "dados" / "complementacoes.json"


def carregar_complementacoes() -> list[dict]:
    """Carrega as complementacoes ficticias fornecidas no desafio."""

    dados = json.loads(
        ARQUIVO_COMPLEMENTACOES.read_text(
            encoding="utf-8-sig"
        )
    )

    if not isinstance(dados, list):
        raise ValueError(
            "Complementacoes devem formar uma lista."
        )

    return dados


def aplicar_complementacao(numero_pedido: str) -> dict:
    """
    Aplica complementacao em copia do pedido original.

    Nao modifica dados/pedidos.json ou complementacoes.json.
    Nao realiza chamada a API.
    """

    correspondentes = [
        item
        for item in carregar_complementacoes()
        if item.get("numero") == numero_pedido
    ]

    if len(correspondentes) != 1:
        raise ValueError(
            "Complementacao inexistente ou duplicada."
        )

    complemento = correspondentes[0]

    data_complementacao = str(
        complemento.get("data") or ""
    )

    date.fromisoformat(data_complementacao)

    texto = complemento.get("texto")

    if not isinstance(texto, str) or not texto.strip():
        raise ValueError(
            "Texto da complementacao ausente."
        )

    original = obter_pedido(numero_pedido)
    pedido = deepcopy(original)

    validacao_original = validar_pedido(original)

    if validacao_original["pode_analisar_merito"]:
        raise ValueError(
            "Pedido original nao apresenta diligencia preliminar."
        )

    alteracoes = {}

    if numero_pedido == "DIA-2026-0111":
        # Extrair uma unica data no formato ISO.
        datas = re.findall(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}",
            texto,
        )

        if len(datas) != 1:
            raise ValueError(
                "Data de retorno nao identificada "
                "de forma inequ?voca."
            )

        retorno = date.fromisoformat(datas[0])
        partida = date.fromisoformat(
            str(pedido["data_partida"])
        )

        if retorno < partida:
            raise ValueError(
                "Retorno anterior a partida."
            )

        if pedido.get("data_retorno") is not None:
            raise ValueError(
                "Data de retorno original nao esta ausente."
            )

        pedido["data_retorno"] = retorno.isoformat()
        alteracoes["data_retorno"] = {
            "anterior": original.get("data_retorno"),
            "corrigido": pedido["data_retorno"],
        }

    elif numero_pedido == "DIA-2026-0112":
        # Extrair uma unica matricula de seis digitos.
        matriculas = re.findall(
            r"(?<![0-9])[0-9]{6}(?![0-9])",
            texto,
        )

        if len(matriculas) != 1:
            raise ValueError(
                "Matricula corrigida nao identificada "
                "de forma inequ?voca."
            )

        matricula = matriculas[0]
        cadastro = consultar_servidor(matricula)

        if "erro" in cadastro:
            raise ValueError(
                "Matricula corrigida nao localizada."
            )

        nome_pedido = str(
            pedido.get("nome") or ""
        ).strip()

        nome_cadastro = str(
            cadastro.get("nome") or ""
        ).strip()

        if nome_pedido.casefold() != nome_cadastro.casefold():
            raise ValueError(
                "Matricula corrigida nao corresponde "
                "ao nome informado no pedido."
            )

        pedido["matricula"] = matricula
        alteracoes["matricula"] = {
            "anterior": original["matricula"],
            "corrigido": matricula,
        }

    else:
        raise ValueError(
            "Pedido sem regra de complementacao autorizada."
        )

    validacao_final = validar_pedido(pedido)

    if not validacao_final["pode_analisar_merito"]:
        raise ValueError(
            "Complementacao nao resolveu as pendencias: "
            + "; ".join(validacao_final["pendencias"])
        )

    return {
        "numero_pedido": numero_pedido,
        "data_complementacao": data_complementacao,
        "texto_complementacao": texto,
        "pedido_original": deepcopy(original),
        "pedido_corrigido": pedido,
        "alteracoes": alteracoes,
        "validacao_original": validacao_original,
        "validacao_corrigida": validacao_final,
        "pode_analisar_merito": True,
    }
