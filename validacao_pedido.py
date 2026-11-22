from ferramentas import consultar_servidor


CAMPOS_OBRIGATORIOS = [
    "numero",
    "matricula",
    "nome",
    "data_pedido",
    "data_partida",
    "data_retorno",
    "destino_municipio",
    "destino_uf",
    "justificativa",
    "transporte",
]


def validar_pedido(pedido: dict) -> dict:
    """
    Verifica completude e correspondencia cadastral.

    Nao consulta historico, calculo ou orcamento.
    """

    pendencias = []

    for campo in CAMPOS_OBRIGATORIOS:
        valor = pedido.get(campo)

        if valor is None or (
            isinstance(valor, str) and not valor.strip()
        ):
            pendencias.append(
                f"Campo obrigatorio ausente: {campo}"
            )

    matricula = str(pedido.get("matricula") or "").strip()
    nome = str(pedido.get("nome") or "").strip()

    if matricula and nome:
        cadastro = consultar_servidor(matricula)

        if "erro" in cadastro:
            pendencias.append(
                "Matricula nao localizada no cadastro."
            )
        else:
            nome_cadastro = str(
                cadastro.get("nome") or ""
            ).strip()

            if nome.casefold() != nome_cadastro.casefold():
                pendencias.append(
                    "Nome informado diverge do cadastro da matricula."
                )

    return {
        "numero_pedido": pedido.get("numero"),
        "pode_analisar_merito": len(pendencias) == 0,
        "recomendacao_preliminar": (
            "prosseguir"
            if not pendencias
            else "diligencia"
        ),
        "pendencias": pendencias,
    }
