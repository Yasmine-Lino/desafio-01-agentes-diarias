"""Persistencia administrativa de pedidos de diarias."""

import json
import re
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import time

from agno.db.base import SessionType
from agno.db.sqlite import SqliteDb
from agno.session.agent import AgentSession
from sqlalchemy import MetaData, Table, inspect, or_, select
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from complementacoes import (
    CAMPOS_COMPLEMENTAVEIS,
    aplicar_complementacao,
    aplicar_correcao,
    obter_pedido,
)
from validacao_pedido import validar_pedido


BASE = Path(__file__).resolve().parent
ARQUIVO_BANCO = BASE / "resultados" / "agente_sessoes.db"
_ACERVO = object()
_INICIALIZACAO_TABELA = Lock()
_CAMPOS_EVENTO = {"data_retorno": "data_retorno", "matricula": "matricula_validada"}
_RESUMOS_ADMINISTRATIVOS = {
    "data_retorno": {
        "motivo_diligencia": "data_retorno_ausente",
        "data_retorno_corrigida_e_validada": True,
    },
    "matricula": {
        "motivo_diligencia": "divergencia_cadastral",
        "matricula_corrigida_e_validada": True,
        "titular_atual_conferido_no_cadastro": True,
    },
}


def obter_banco(caminho_banco=None):
    """Abre o adaptador de sessoes no caminho indicado ou no banco de trabalho."""
    caminho = Path(caminho_banco) if caminho_banco is not None else ARQUIVO_BANCO
    return SqliteDb(db_file=str(caminho))


def criar_evento(tipo, dados):
    """Cria evento administrativo sem simular execucao de IA."""
    return {
        "tipo": tipo,
        "registrado_em": datetime.now(timezone.utc).isoformat(),
        "dados": deepcopy(dados),
    }


@contextmanager
def _transacao_sessoes(caminho_banco, *, criar=False, escrita=False, banco_protegido=None):
    banco = None
    try:
        if banco_protegido is not None:
            if caminho_banco is None or banco_protegido.db_file != str(Path(caminho_banco).resolve()):
                raise ValueError("Banco protegido nao corresponde ao caminho de trabalho.")
            banco = banco_protegido
        else:
            banco = obter_banco(caminho_banco) if caminho_banco is not None else obter_banco()
        # Usa o esquema da versao instalada do Agno e atualiza apenas a sessao.
        with _INICIALIZACAO_TABELA:
            try:
                tabela = banco._get_table("sessions", create_table_if_not_found=criar)
            except OperationalError as erro:
                if not criar or "already exists" not in str(erro.orig).lower():
                    raise
                # Outro processo venceu a criacao do esquema antes da transacao.
                tabela = banco._get_table("sessions")
        if tabela is None:
            raise ValueError("Diligencia inicial nao encontrada.")
        with banco.db_engine.begin() as conexao:
            conexao.exec_driver_sql("BEGIN IMMEDIATE" if escrita else "BEGIN")
            yield conexao, tabela, banco.runs_table_name
    except (OSError, SQLAlchemyError):
        raise RuntimeError("Falha na persistencia administrativa da sessao.") from None
    finally:
        if banco is not None and banco_protegido is None:
            banco.close()


def _ler_sessao(conexao, tabela, numero):
    return conexao.execute(
        select(
            tabela.c.session_id, tabela.c.user_id, tabela.c.agent_id,
            tabela.c.session_type, tabela.c.metadata,
            tabela.c.created_at, tabela.c.updated_at,
        ).where(tabela.c.session_id == numero)
    ).mappings().one_or_none()


def _ler_eventos(sessao, numero):
    meta = sessao["metadata"]
    if (
        sessao["session_type"] != SessionType.AGENT.value
        or not isinstance(meta, dict) or meta.get("numero_pedido") != numero
    ):
        raise ValueError("Sessao administrativa nao corresponde ao pedido.")

    eventos = meta.get("eventos_administrativos")
    if not isinstance(eventos, list) or not all(isinstance(evento, dict) for evento in eventos):
        raise ValueError("Eventos administrativos invalidos.")
    tipos = [evento.get("tipo") for evento in eventos]
    estado = meta.get("estado")
    if estado == "aguardando_complementacao" and tipos == ["diligencia_preliminar"]:
        if sessao["user_id"] is not None:
            raise ValueError("Sessao preliminar possui titular divergente.")
    elif not (estado == "complementado" and tipos == ["diligencia_preliminar", "complementacao"]):
        raise ValueError("Estado administrativo da sessao invalido.")

    registros = []
    for evento in eventos:
        try:
            if evento.keys() != {"tipo", "registrado_em", "dados"}:
                raise ValueError
            registro = datetime.fromisoformat(evento["registrado_em"])
            if registro.tzinfo is None or not isinstance(evento["dados"], dict):
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError("Registro de evento administrativo invalido.") from None
        registros.append(registro)
    if registros != sorted(registros):
        raise ValueError("Ordem cronologica dos eventos administrativos invalida.")
    return meta, eventos


def _sessao_administrativa(sessao, meta):
    return AgentSession(
        session_id=sessao["session_id"],
        user_id=sessao["user_id"],
        agent_id=sessao["agent_id"],
        metadata={chave: deepcopy(meta[chave]) for chave in (
            "numero_pedido", "estado", "eventos_administrativos"
        )},
        created_at=sessao["created_at"],
        updated_at=sessao["updated_at"],
    )


def _correcao_registrada(numero, sessao, eventos):
    campo = CAMPOS_COMPLEMENTAVEIS.get(numero)
    dados = eventos[-1].get("dados")
    if (
        campo is None
        or dados.keys() != {_CAMPOS_EVENTO[campo], "pedido_apto_para_analise"}
        or dados["pedido_apto_para_analise"] is not True
    ):
        raise ValueError("Complementacao administrativa invalida.")
    correcao = aplicar_correcao(numero, {campo: dados.get(_CAMPOS_EVENTO[campo])})
    if eventos[0]["dados"] != {"pendencias": correcao["validacao_original"]["pendencias"]}:
        raise ValueError("Diligencia persistida diverge da validacao do pedido original.")
    if sessao["user_id"] != correcao["pedido_corrigido"]["matricula"]:
        raise ValueError("Titular da sessao diverge da complementacao validada.")
    return correcao


def _conferir_titular_das_execucoes(conexao, sessoes, nome_runs, numero, titular):
    coluna_legada = sessoes.c.get("runs")
    if coluna_legada is not None:
        legado = conexao.execute(
            select(coluna_legada).where(sessoes.c.session_id == numero)
        ).scalar_one()
        if isinstance(legado, str):
            legado = json.loads(legado)
        if legado is not None and (
            not isinstance(legado, list)
            or any(
                titular is None or not isinstance(run, dict) or run.get("user_id") != titular
                for run in legado
            )
        ):
            raise ValueError("Sessao possui execucoes incompativeis com o titular validado.")

    if not inspect(conexao).has_table(nome_runs):
        return
    runs = Table(nome_runs, MetaData(), autoload_with=conexao)
    filtro = runs.c.session_id == numero
    if titular is not None:
        filtro = filtro & or_(runs.c.user_id.is_(None), runs.c.user_id != titular)
    if conexao.execute(select(runs.c.run_id).where(filtro).limit(1)).first() is not None:
        raise ValueError("Sessao possui execucoes incompativeis com o titular validado.")


def registrar_diligencia(numero, *, caminho_banco=None, banco_protegido=None):
    """Registra uma vez a diligencia local, sem vincular matricula nao validada."""
    if not isinstance(numero, str) or re.fullmatch(r"DIA-[0-9]{4}-[0-9]{4}", numero) is None:
        raise ValueError("Protocolo invalido.")
    pedido = obter_pedido(numero)
    validacao = validar_pedido(pedido)
    if validacao["pode_analisar_merito"]:
        raise ValueError("Pedido nao exige diligencia preliminar.")

    with _transacao_sessoes(
        caminho_banco, criar=True, escrita=True, banco_protegido=banco_protegido,
    ) as (conexao, tabela, nome_runs):
        sessao = _ler_sessao(conexao, tabela, numero)
        if sessao is not None:
            meta, eventos = _ler_eventos(sessao, numero)
            if meta["estado"] == "complementado":
                _correcao_registrada(numero, sessao, eventos)
            _conferir_titular_das_execucoes(conexao, tabela, nome_runs, numero, sessao["user_id"])
            return _sessao_administrativa(sessao, meta)

        agora = int(time())
        meta = {
            "numero_pedido": numero,
            "estado": "aguardando_complementacao",
            "eventos_administrativos": [
                criar_evento("diligencia_preliminar", {"pendencias": validacao["pendencias"]})
            ],
        }
        sessao = {
            "session_id": numero,
            "session_type": SessionType.AGENT.value,
            "agent_id": "agente_diarias",
            "user_id": None,
            "created_at": agora,
            "updated_at": agora,
        }
        conexao.execute(tabela.insert().values(**sessao, metadata=meta))
        return _sessao_administrativa(sessao, meta)


def registrar_complementacao(numero, correcao=_ACERVO, *, caminho_banco=None, banco_protegido=None):
    """Registra o recebimento validado e deixa a sessao pronta para nova execucao."""
    complemento = (
        aplicar_complementacao(numero) if correcao is _ACERVO else aplicar_correcao(numero, correcao)
    )
    pedido = complemento["pedido_corrigido"]
    campo = CAMPOS_COMPLEMENTAVEIS[numero]
    with _transacao_sessoes(
        caminho_banco, escrita=True, banco_protegido=banco_protegido,
    ) as (conexao, tabela, nome_runs):
        sessao = _ler_sessao(conexao, tabela, numero)
        if sessao is None:
            raise ValueError("Diligencia inicial nao encontrada.")
        meta, eventos = _ler_eventos(sessao, numero)
        _conferir_titular_das_execucoes(conexao, tabela, nome_runs, numero, sessao["user_id"])
        if meta["estado"] == "complementado":
            anterior = _correcao_registrada(numero, sessao, eventos)
            if anterior["alteracoes"] != complemento["alteracoes"]:
                raise ValueError("Sessao ja possui uma complementacao diferente.")
            return _sessao_administrativa(sessao, meta)

        evento = criar_evento("complementacao", {
            _CAMPOS_EVENTO[campo]: pedido[campo],
            "pedido_apto_para_analise": True,
        })
        meta = {
            **meta,
            "estado": "complementado",
            "eventos_administrativos": [*eventos, evento],
        }
        atualizado = {"user_id": pedido["matricula"], "updated_at": int(time())}
        conexao.execute(
            tabela.update().where(tabela.c.session_id == numero).values(**atualizado, metadata=meta)
        )
        return _sessao_administrativa({**sessao, **atualizado}, meta)


def preparar_pedido_complementado(numero, *, caminho_banco=None):
    """Recupera a correção e projeta os eventos validados em um resumo sem texto livre."""
    with _transacao_sessoes(caminho_banco) as (conexao, tabela, nome_runs):
        sessao = _ler_sessao(conexao, tabela, numero)
        if sessao is None:
            raise ValueError("Diligencia inicial nao encontrada.")
        meta, eventos = _ler_eventos(sessao, numero)
        if meta["estado"] != "complementado":
            raise ValueError("Sessao ainda aguarda complementacao.")
        pedido = _correcao_registrada(numero, sessao, eventos)["pedido_corrigido"]
        _conferir_titular_das_execucoes(conexao, tabela, nome_runs, numero, sessao["user_id"])
        return {
            "pedido_corrigido": pedido,
            "session_id": numero,
            "user_id": sessao["user_id"],
            "resumo_administrativo": _RESUMOS_ADMINISTRATIVOS[CAMPOS_COMPLEMENTAVEIS[numero]].copy(),
        }
