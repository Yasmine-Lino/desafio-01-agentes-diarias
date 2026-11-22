import json
import re
from copy import deepcopy
from datetime import date
from pathlib import Path

from ferramentas import consultar_servidor
from validacao_pedido import validar_pedido


BASE = Path(__file__).resolve().parent
ARQUIVO_COMPLEMENTACOES = BASE / "dados" / "complementacoes.json"
CAMPOS_COMPLEMENTAVEIS = {
    "DIA-2026-0111": "data_retorno",
    "DIA-2026-0112": "matricula",
}


def carregar_complementacoes() -> list[dict]:
    """Carrega as complementacoes ficticias fornecidas no desafio."""
    dados = json.loads(ARQUIVO_COMPLEMENTACOES.read_text(encoding="utf-8-sig"))
    if not isinstance(dados, list):
        raise ValueError("Complementacoes devem formar uma lista.")
    return dados


def obter_pedido(numero_pedido: str) -> dict:
    """Consulta somente o acervo operacional, sem inicializar o agente."""
    arquivo = BASE / "dados" / "pedidos.json"
    dados = json.loads(arquivo.read_text(encoding="utf-8-sig"))
    pedidos = [item for item in dados if item.get("numero") == numero_pedido]
    if len(pedidos) != 1:
        raise ValueError("Pedido nao localizado de forma inequivoca.")
    return pedidos[0]


def _data_iso(valor):
    if not isinstance(valor, str):
        raise ValueError("Data da complementacao invalida.")
    try:
        data = date.fromisoformat(valor)
    except ValueError:
        raise ValueError("Data da complementacao invalida.") from None
    if data.isoformat() != valor:
        raise ValueError("Use o formato AAAA-MM-DD para a data.")
    return data


def aplicar_correcao(numero_pedido: str, correcao: dict) -> dict:
    """Valida uma correcao estruturada, limitada ao campo em diligencia."""
    campo = CAMPOS_COMPLEMENTAVEIS.get(numero_pedido)
    if campo is None or not isinstance(correcao, dict) or correcao.keys() != {campo}:
        raise ValueError("Informe somente o campo permitido para a complementacao.")

    original = obter_pedido(numero_pedido)
    validacao_original = validar_pedido(original)
    if validacao_original["pode_analisar_merito"]:
        raise ValueError("Pedido original nao apresenta diligencia preliminar.")

    valor = correcao[campo]
    if campo == "data_retorno":
        retorno = _data_iso(valor)
        partida = _data_iso(original.get("data_partida"))
        if retorno < partida:
            raise ValueError("Retorno anterior a partida.")
        if original.get("data_retorno") is not None:
            raise ValueError("Data de retorno original nao esta ausente.")
    else:
        if not isinstance(valor, str) or re.fullmatch(r"[0-9]{6}", valor) is None:
            raise ValueError("Matricula corrigida deve conter seis digitos ASCII.")
        cadastro = consultar_servidor(valor)
        nome = str(original.get("nome") or "").strip()
        nome_cadastro = str(cadastro.get("nome") or "").strip()
        if cadastro.get("encontrado") is not True or not nome or nome.casefold() != nome_cadastro.casefold():
            raise ValueError("Matricula corrigida nao corresponde ao cadastro do pedido.")

    pedido = deepcopy(original)
    pedido[campo] = valor
    validacao_final = validar_pedido(pedido)
    if not validacao_final["pode_analisar_merito"]:
        raise ValueError("Complementacao nao resolveu as pendencias.")

    return {
        "numero_pedido": numero_pedido,
        "pedido_original": original,
        "pedido_corrigido": pedido,
        "alteracoes": {campo: {"anterior": original.get(campo), "corrigido": valor}},
        "validacao_original": validacao_original,
        "validacao_corrigida": validacao_final,
        "pode_analisar_merito": True,
    }


def aplicar_complementacao(numero_pedido: str) -> dict:
    """Adapta a resposta do acervo para os scripts de demonstracao."""
    campo = CAMPOS_COMPLEMENTAVEIS.get(numero_pedido)
    if campo is None:
        raise ValueError("Pedido sem regra de complementacao autorizada.")

    correspondentes = [
        item for item in carregar_complementacoes() if item.get("numero") == numero_pedido
    ]
    if len(correspondentes) != 1:
        raise ValueError("Complementacao inexistente ou duplicada.")

    complemento = correspondentes[0]
    data = _data_iso(complemento.get("data"))
    texto = complemento.get("texto")
    if not isinstance(texto, str) or not texto.strip():
        raise ValueError("Texto da complementacao ausente.")
    padrao = (
        r"(?<![0-9])[0-9]{4}-[0-9]{2}-[0-9]{2}(?![0-9])"
        if campo == "data_retorno" else r"(?<![0-9])[0-9]{6}(?![0-9])"
    )
    valores = re.findall(padrao, texto)
    if len(valores) != 1:
        raise ValueError("Correcao nao identificada de forma inequivoca.")
    return {
        **aplicar_correcao(numero_pedido, {campo: valores[0]}),
        "data_complementacao": data.isoformat(),
        "texto_complementacao": texto,
    }
