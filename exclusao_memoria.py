"""Exclusão lógica na cópia de trabalho SQLite do Agno 3.2.1."""

import json
import re
import sqlite3
from collections import Counter
from importlib.metadata import version
from pathlib import Path
from unicodedata import normalize

from sqlalchemy.exc import SQLAlchemyError

from barreira_persistente import (
    BarreiraPersistente, TABELAS_AGNO, adaptar_agno, caminho_validado, conferir_esquema, reservar_escrita,
)
from complementacoes import CAMPOS_COMPLEMENTAVEIS, aplicar_correcao
from ferramentas import consultar_servidor


_TABELAS = {
    "sessoes": "agno_sessions",
    "execucoes": "agno_runs",
    "memorias": "agno_memories",
}
_CAMPOS_RESIDUOS = {
    "agno_sessions": (
        ("session_id", "session_type", "agent_id", "team_id", "workflow_id", "user_id"),
        ("session_data", "agent_data", "team_data", "workflow_data", "metadata", "summary", "runs"),
    ),
    "agno_runs": (
        ("run_id", "session_id", "run_type", "agent_id", "team_id", "workflow_id",
         "user_id", "parent_run_id", "status"),
        ("run_data",),
    ),
    "agno_memories": (
        ("memory_id", "input", "agent_id", "team_id", "user_id", "feedback"),
        ("memory", "topics"),
    ),
}
_CAMPOS_JSON_NAO_NULOS = {"run_data", "memory"}


def _linhas(conexao):
    conferir_esquema(conexao)
    tabelas = {nome for (nome,) in conexao.exec_driver_sql(
        "SELECT name FROM main.sqlite_schema WHERE type = 'table'"
    )}
    return {
        tabela: [dict(linha) for linha in conexao.exec_driver_sql(f'SELECT * FROM main."{tabela}"').mappings()]
        if tabela in tabelas else []
        for tabela in sorted(TABELAS_AGNO)
    }


def _inventariar(linhas, matricula):
    sessoes = {linha["session_id"]: linha for linha in linhas["agno_sessions"]}
    conflitos = Counter()
    for sessao in sessoes.values():
        titular = sessao["user_id"]
        if titular is None:
            conflitos["sessao_sem_titular"] += 1
        if sessao.get("runs") is not None and json.loads(sessao["runs"]) not in (None, []):
            conflitos["historico_legado_nao_resolvido"] += 1
        if titular == matricula and sessao["session_type"] != "agent":
            conflitos["tipo_de_sessao_incompativel"] += 1
        protocolo = sessao["session_id"]
        if protocolo in CAMPOS_COMPLEMENTAVEIS and titular is not None:
            meta = json.loads(sessao["metadata"] or "null")
            if not _vinculo_complementado(protocolo, meta, titular):
                conflitos["titular_da_complementacao_nao_confirmado"] += 1

    for run in linhas["agno_runs"]:
        sessao = sessoes.get(run["session_id"])
        if sessao is None:
            conflitos["execucao_orfa"] += 1
        elif run["user_id"] is None or run["user_id"] != sessao["user_id"]:
            conflitos["titular_da_execucao_incompativel"] += 1
        dados = json.loads(run["run_data"])
        if not isinstance(dados, dict) or any(
            dados.get(campo) != run[campo] for campo in ("run_id", "session_id", "user_id")
        ):
            conflitos["identidade_da_execucao_inconsistente"] += 1

    conflitos["memoria_sem_titular"] = sum(linha["user_id"] is None for linha in linhas["agno_memories"])
    return {motivo: total for motivo, total in sorted(conflitos.items()) if total}


def _vinculo_complementado(protocolo, meta, titular):
    eventos = meta.get("eventos_administrativos") if isinstance(meta, dict) else None
    if (
        not isinstance(eventos, list)
        or len(eventos) != 2
        or not all(isinstance(evento, dict) for evento in eventos)
        or [evento.get("tipo") for evento in eventos] != ["diligencia_preliminar", "complementacao"]
        or meta.get("numero_pedido") != protocolo
        or meta.get("estado") != "complementado"
    ):
        return False
    campo = CAMPOS_COMPLEMENTAVEIS[protocolo]
    chave = "matricula_validada" if campo == "matricula" else campo
    dados = eventos[1].get("dados")
    if (
        not isinstance(dados, dict)
        or dados.keys() != {chave, "pedido_apto_para_analise"}
        or dados["pedido_apto_para_analise"] is not True
    ):
        return False
    try:
        correcao = aplicar_correcao(protocolo, {campo: dados[chave]})
    except ValueError:
        return False
    return (
        correcao["pedido_corrigido"]["matricula"] == titular
        and eventos[0].get("dados") == {"pendencias": correcao["validacao_original"]["pendencias"]}
    )


def _contagens(linhas, matricula):
    return {
        tipo: sum(linha["user_id"] == matricula for linha in linhas[tabela])
        for tipo, tabela in _TABELAS.items()
    }


def _ler_json_residuos(valor):
    def rejeitar_constante(_constante):
        raise ValueError("constante_json_invalida")

    # Preserva todas as chaves e valores, inclusive chaves repetidas.
    return json.loads(valor, object_pairs_hook=list, parse_constant=rejeitar_constante)


def _examinar_campo(valor, corresponde, *, campo_json):
    if valor is None:
        return False, False
    if not isinstance(valor, str):
        return False, True

    encontrou = corresponde(valor)
    pendentes = []
    if campo_json:
        try:
            pendentes.append(_ler_json_residuos(valor))
        except (ValueError, RecursionError):
            return encontrou, True
    else:
        pendentes.append(valor)

    # Campos TEXT e strings dentro de JSON também podem carregar JSON serializado.
    # Uma string comum continua sujeita à busca literal, mesmo se começar com '{'.
    incompleto = False
    while pendentes:
        item = pendentes.pop()
        if isinstance(item, (list, tuple)):
            pendentes.extend(item)
        elif isinstance(item, str):
            encontrou |= corresponde(item)
            if item.lstrip().startswith(("{", "[", '"')):
                try:
                    pendentes.append(_ler_json_residuos(item))
                except ValueError:
                    pass
                except RecursionError:
                    incompleto = True
        elif type(item) in (int, float):
            encontrou |= corresponde(str(item))
    return encontrou, incompleto


def _normalizar_nome(texto):
    return normalize("NFC", " ".join(texto.casefold().split()))


def _residuos(linhas, matricula, nome):
    padrao = re.compile(rf"(?<![0-9]){matricula}(?![0-9])")
    padrao_nome = re.compile(rf"(?<!\w){re.escape(_normalizar_nome(nome))}(?!\w)") if nome else None

    def corresponde(valor):
        return bool(padrao.search(valor) or (padrao_nome and padrao_nome.search(_normalizar_nome(valor))))

    contagens = Counter()
    incompletos = 0
    for tabela, (textos, campos_json) in _CAMPOS_RESIDUOS.items():
        for linha in linhas[tabela]:
            encontrou = incompleto = False
            for coluna in (*textos, *campos_json):
                valor = linha.get(coluna)
                if valor is None and coluna in _CAMPOS_JSON_NAO_NULOS:
                    incompleto = True
                    continue
                achou, falhou = _examinar_campo(valor, corresponde, campo_json=coluna in campos_json)
                encontrou |= achou
                incompleto |= falhou
            if encontrou:
                contagens[tabela] += 1
            incompletos += incompleto
    return dict(contagens), incompletos


def _excluir(conexao, banco, barreira, matricula, relatorio):
    linhas = _linhas(conexao)
    antes = _contagens(linhas, matricula)
    cadastro = consultar_servidor(matricula)
    nome = cadastro.get("nome")
    nome = nome.strip() if (
        cadastro.get("encontrado") is True and cadastro.get("matricula") == matricula and isinstance(nome, str)
    ) else ""
    residuos, incompletos = _residuos(linhas, matricula, nome)
    relatorio.update(
        antes=antes, depois=antes.copy(), residuos=residuos,
        nome_verificado=bool(nome),
        sessoes_verificadas=len(linhas["agno_sessions"]),
        memorias_verificadas=len(linhas["agno_memories"]),
    )
    if incompletos:
        relatorio["conflitos"]["inspecao_residuos_incompleta"] = incompletos
        return "bloqueado"
    conflitos = _inventariar(linhas, matricula)
    if not barreira.conferir_protocolos(conexao, linhas["agno_sessions"]):
        conflitos["protocolo_com_vinculo_divergente"] = 1
    relatorio["conflitos"] = conflitos
    if conflitos:
        return "bloqueado"
    if not any(antes.values()):
        return "sem_registros"

    sessoes = [linha for linha in linhas["agno_sessions"] if linha["user_id"] == matricula]
    barreira.vincular_verificados(conexao, sessoes, matricula)
    # As APIs executam suas transações em savepoints da mesma conexão bloqueada.
    try:
        with conexao.begin_nested():
            for linha in sessoes:
                if not banco.delete_session(linha["session_id"], user_id=matricula):
                    raise RuntimeError("sessao_nao_excluida")
            ids = [linha["memory_id"] for linha in linhas["agno_memories"] if linha["user_id"] == matricula]
            if ids:
                banco.delete_user_memories(ids, user_id=matricula)

            atuais = _linhas(conexao)
            residuos_apos, incompletos = _residuos(atuais, matricula, nome)
            if incompletos:
                relatorio["conflitos"]["inspecao_residuos_incompleta"] = incompletos
                raise RuntimeError("conferencia_pos_exclusao_incompleta")
            novos_conflitos = _inventariar(atuais, matricula)
            for tabela, registros in linhas.items():
                esperados = [linha for linha in registros if linha.get("user_id") != matricula]
                encontrados = Counter(tuple(linha.items()) for linha in atuais[tabela])
                if novos_conflitos or encontrados != Counter(tuple(linha.items()) for linha in esperados):
                    raise RuntimeError("conferencia_pos_exclusao_falhou")
    except (OSError, RuntimeError, SQLAlchemyError, ValueError):
        relatorio["conflitos"]["exclusao_revertida"] = 1
        return "erro"

    relatorio.update(depois=_contagens(atuais, matricula), residuos=residuos_apos)
    return "excluido"


def excluir_memoria_titular(matricula, *, caminho_banco: Path, banco_autorizado: Path, barreira=None):
    """Usa a matrícula já autorizada e o caminho absoluto fixado pelo chamador confiável.

    Relata resultados lógicos e contagens. A autenticação do solicitante é do chamador.
    """
    relatorio = {
        "status": "bloqueado", "antes": None, "depois": None,
        "sessoes_verificadas": 0, "memorias_verificadas": 0,
        "conflitos": {}, "residuos": {}, "nome_verificado": False,
        "revisao_manual": True, "bloqueio_confirmado": False,
    }
    if not isinstance(matricula, str) or re.fullmatch(r"[0-9]{6}", matricula) is None:
        relatorio["conflitos"]["matricula_invalida"] = 1
        return relatorio
    caminho = caminho_validado(caminho_banco, banco_autorizado)
    if caminho is None:
        relatorio["conflitos"]["banco_nao_autorizado"] = 1
        return relatorio
    if version("agno") != "3.2.1":
        relatorio["conflitos"]["adaptador_nao_validado"] = 1
        return relatorio
    if not isinstance(barreira, BarreiraPersistente):
        relatorio["conflitos"]["barreira_nao_configurada"] = 1
        return relatorio

    engine = barreira._engine(caminho)
    try:
        # O bloqueio sobrevive mesmo se a segunda transação nunca começar.
        with engine.begin() as conexao:
            reservar_escrita(conexao)
            with adaptar_agno(engine, conexao) as banco:
                barreira.preparar_na_transacao(conexao, banco)
                barreira.registrar_pendente(conexao, matricula)
        relatorio["bloqueio_confirmado"] = True
        with engine.begin() as conexao:
            reservar_escrita(conexao)
            conferir_esquema(conexao)
            barreira.conferir_chave(conexao)
            with adaptar_agno(engine, conexao) as banco:
                status = _excluir(conexao, banco, barreira, matricula, relatorio)
            revisao = status in {"bloqueado", "erro"} or bool(relatorio["residuos"]) or not relatorio["nome_verificado"]
            barreira.registrar_estado(conexao, matricula, "revisao_manual" if revisao else "concluida")
        relatorio["status"] = status
        relatorio["revisao_manual"] = revisao
    except (OSError, RuntimeError, SQLAlchemyError, ValueError, KeyError) as erro:
        codigo = getattr(getattr(erro, "orig", erro), "sqlite_errorcode", 0) or 0
        if (codigo & 255) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
            motivo = "escrita_concorrente"
        elif isinstance(erro, ValueError) and erro.args in {
            ("esquema_nao_suportado",), ("chave_da_barreira_incompativel",),
        }:
            motivo = erro.args[0]
        else:
            motivo = "inventario_ou_transacao_indisponivel"
        relatorio["conflitos"][motivo] = 1
        relatorio["depois"] = None
    finally:
        engine.dispose()
    return relatorio
