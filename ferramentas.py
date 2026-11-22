import csv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DADOS_DIR = BASE_DIR / "dados"


def consultar_servidor(matricula: str) -> dict:
    """Confira a identidade e a lotação antes de consultar diárias.

    Informe a matrícula como texto de dígitos, preservando zeros à esquerda.
    Retorna encontrado, matrícula, nome, cargo, grupo, unidade e sede em caso
    de sucesso, sem CPF ou e-mail. Matrícula inválida, inexistente ou cadastro
    indisponível retornam encontrado=False e uma mensagem de erro.
    """

    matricula = str(matricula).strip()

    if not matricula or not matricula.isdigit():
        return {
            "encontrado": False,
            "erro": "Matricula invalida"
        }

    arquivo = DADOS_DIR / "servidores.csv"

    if not arquivo.is_file():
        return {
            "encontrado": False,
            "erro": "Cadastro indisponivel"
        }

    with arquivo.open("r", encoding="utf-8-sig", newline="") as f:
        leitor = csv.DictReader(f)

        for servidor in leitor:
            if servidor["matricula"].strip() == matricula:
                return {
                    "encontrado": True,
                    "matricula": servidor["matricula"],
                    "nome": servidor["nome"],
                    "cargo": servidor["cargo"],
                    "grupo_diaria": servidor["grupo_diaria"],
                    "unidade": servidor["unidade"],
                    "municipio_sede": servidor["municipio_sede"]
                }

    return {
        "encontrado": False,
        "matricula": matricula,
        "erro": "Servidor nao encontrado"
    }

from datetime import date, timedelta
from decimal import Decimal


def adicionar_dias_uteis(data_inicial: date, quantidade: int) -> date:
    """Conta dias de segunda a sexta, sem calendario de feriados."""
    atual = data_inicial
    adicionados = 0

    while adicionados < quantidade:
        atual += timedelta(days=1)
        if atual.weekday() < 5:
            adicionados += 1

    return atual


def consultar_historico(
    matricula: str,
    mes_referencia: str,
    data_analise: str = "2026-10-09"
) -> dict:
    """Confira o acumulado mensal e pendências do servidor após validar o cadastro.

    Informe matrícula em dígitos, mes_referencia no formato AAAA-MM e
    data_analise em AAAA-MM-DD como corte do exame de vencimento.
    Retorna total de diárias no mês, indicador e pedidos com prestação vencida
    e registros consultados. Formato inválido ou histórico indisponível retorna erro.
    """

    matricula = str(matricula).strip()

    if not matricula.isdigit():
        return {"erro": "Matricula invalida"}

    try:
        ano, mes = map(int, mes_referencia.split("-"))
        date(ano, mes, 1)
        analise = date.fromisoformat(data_analise)
    except (ValueError, TypeError):
        return {"erro": "Data ou mes de referencia invalido"}

    arquivo = DADOS_DIR / "historico_diarias.csv"

    if not arquivo.is_file():
        return {"erro": "Historico indisponivel"}

    registros = []
    total_mes = Decimal("0")
    pendencias_vencidas = []

    with arquivo.open("r", encoding="utf-8-sig", newline="") as f:
        for linha in csv.DictReader(f):
            if linha["matricula"].strip() != matricula:
                continue

            try:
                partida = date.fromisoformat(linha["data_partida"])
                retorno = date.fromisoformat(linha["data_retorno"])
                quantidade = Decimal(linha["quantidade"])
            except (ValueError, KeyError):
                return {"erro": "Registro historico invalido"}

            if partida.year == ano and partida.month == mes:
                total_mes += quantidade

            situacao = linha["prestacao_contas"].strip().lower()
            prazo = adicionar_dias_uteis(retorno, 5)

            vencida = (
                situacao != "entregue"
                and prazo < analise
            )

            registro = {
                "pedido": linha["pedido"],
                "data_partida": partida.isoformat(),
                "data_retorno": retorno.isoformat(),
                "quantidade": float(quantidade),
                "prestacao_contas": situacao,
                "prazo_prestacao": prazo.isoformat(),
                "prestacao_vencida": vencida
            }

            registros.append(registro)

            if vencida:
                pendencias_vencidas.append(linha["pedido"])

    return {
        "matricula": matricula,
        "mes_referencia": mes_referencia,
        "data_analise": analise.isoformat(),
        "total_diarias_mes": float(total_mes),
        "possui_prestacao_vencida": bool(pendencias_vencidas),
        "pedidos_vencidos": pendencias_vencidas,
        "registros": registros
    }

import json


def calcular_diarias(
    matricula: str,
    destino_uf: str,
    data_partida: str,
    data_retorno: str,
    mes_referencia: str,
    data_analise: str = "2026-10-09",
    *,
    data_pedido: str,
) -> dict:
    """Calcule quantidade, valor, antecedência e limite após conferir o cadastro.

    Informe matrícula em dígitos, destino_uf com a sigla de duas letras,
    mes_referencia em AAAA-MM e as datas em AAAA-MM-DD. data_pedido é a
    data do protocolo e data_analise é o corte da análise.
    Retorna grupo, destino, quantidade, valores unitário e total, antecedência
    e acumulado e limite mensal. Cadastro, datas, destino, histórico ou tabela
    incompatíveis ou indisponíveis produzem erro em vez de valores presumidos.
    """

    servidor = consultar_servidor(matricula)

    if not servidor.get("encontrado"):
        return {"erro": "Servidor nao encontrado"}

    try:
        partida = date.fromisoformat(data_partida)
        retorno = date.fromisoformat(data_retorno)
        analise = date.fromisoformat(data_analise)
        protocolo = date.fromisoformat(data_pedido)
        if protocolo.isoformat() != data_pedido:
            return {"erro": "Data do protocolo invalida"}
        if protocolo > partida:
            return {"erro": "Protocolo posterior a partida"}

        if retorno < partida:
            return {"erro": "Retorno anterior a partida"}

        if partida < analise:
            return {"erro": "Partida anterior a data de analise"}

        tabela = json.loads(
            (DADOS_DIR / "tabela_diarias.json").read_text(
                encoding="utf-8-sig"
            )
        )

        uf = destino_uf.strip().upper()

        if uf == "MT":
            categoria = "interior_mt"
        elif uf == "DF":
            categoria = "distrito_federal"
        elif len(uf) == 2 and uf.isalpha():
            categoria = "outra_uf"
        else:
            return {"erro": "UF invalida"}

        grupo = servidor["grupo_diaria"]

        valor_unitario = Decimal(
            str(tabela["valores"][grupo][categoria])
        )

        dias = (retorno - partida).days

        quantidade = Decimal("0.5") if dias == 0 else (
            Decimal(dias) + Decimal("0.5")
        )

        valor_total = quantidade * valor_unitario

        antecedencia = (partida - protocolo).days
        minimo = int(tabela["antecedencia_minima_dias"])

        historico = consultar_historico(
            matricula,
            mes_referencia,
            data_analise
        )

        if "erro" in historico:
            return {"erro": historico["erro"]}

        acumulado = Decimal(
            str(historico["total_diarias_mes"])
        )

        limite = Decimal(
            str(tabela["limite_mensal_diarias"])
        )

        total_projetado = acumulado + quantidade

        return {
            "matricula": str(matricula),
            "grupo_diaria": grupo,
            "categoria_destino": categoria,
            "data_partida": partida.isoformat(),
            "data_retorno": retorno.isoformat(),
            "quantidade_diarias": float(quantidade),
            "valor_unitario": float(valor_unitario),
            "valor_total": float(valor_total),
            "antecedencia_dias": antecedencia,
            "antecedencia_atendida": antecedencia >= minimo,
            "diarias_anteriores_mes": float(acumulado),
            "total_projetado_mes": float(total_projetado),
            "limite_mensal": float(limite),
            "limite_mensal_atendido": total_projetado <= limite
        }

    except (ValueError, KeyError, TypeError, OSError) as exc:
        return {
            "erro": "Dados invalidos ou tabela indisponivel",
            "tipo": type(exc).__name__
        }


def consultar_saldo(matricula: str, valor_solicitado: float) -> dict:
    """Verifique a cobertura da unidade após obter o valor total do cálculo.

    Informe a matrícula em dígitos e valor_solicitado como número em reais,
    positivo e finito. A unidade vem do cadastro da matrícula.
    Retorna unidade, saldo disponível, valor solicitado, saldo projetado e
    indicação de suficiência. Cadastro, valor ou dotação inválidos ou
    indisponíveis produzem erro.
    """

    servidor = consultar_servidor(matricula)

    if not servidor.get("encontrado"):
        return {"erro": "Servidor nao encontrado"}

    try:
        valor = Decimal(str(valor_solicitado))

        if not valor.is_finite() or valor <= 0:
            return {"erro": "Valor solicitado invalido"}

        arquivo = DADOS_DIR / "unidades.json"

        unidades = json.loads(
            arquivo.read_text(encoding="utf-8-sig")
        )

        sigla = servidor["unidade"]

        if sigla not in unidades:
            return {"erro": "Unidade orcamentaria nao encontrada"}

        unidade = unidades[sigla]
        saldo = Decimal(str(unidade["saldo_diarias"]))

        if not saldo.is_finite() or saldo < 0:
            return {"erro": "Saldo orcamentario invalido"}

        suficiente = saldo >= valor

        return {
            "matricula": str(matricula),
            "unidade": sigla,
            "nome_unidade": unidade["nome"],
            "saldo_disponivel": float(saldo),
            "valor_solicitado": float(valor),
            "saldo_suficiente": suficiente,
            "saldo_apos_solicitacao": float(saldo - valor)
        }

    except (ValueError, TypeError, KeyError, OSError):
        return {"erro": "Falha na consulta orcamentaria"}
