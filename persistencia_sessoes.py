"""Persistencia administrativa de pedidos de diarias."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from agno.db.sqlite import SqliteDb
from agno.session.agent import AgentSession

from agente import BASE, obter_pedido
from complementacoes import aplicar_complementacao
from validacao_pedido import validar_pedido


ARQUIVO_BANCO = BASE / "resultados" / "agente_sessoes.db"


def obter_banco():
    """Cria acesso ao banco SQLite do projeto."""
    ARQUIVO_BANCO.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    return SqliteDb(db_file=str(ARQUIVO_BANCO))


def criar_evento(tipo, dados):
    """Cria evento administrativo sem simular execucao de IA."""
    return {
        "tipo": tipo,
        "registrado_em": datetime.now(
            timezone.utc
        ).isoformat(),
        "dados": deepcopy(dados),
    }


def registrar_diligencia(numero):
    """Registra a diligencia inicial de um pedido incompleto."""
    banco = obter_banco()

    if banco.get_session(numero) is not None:
        raise ValueError(
            "Sessao ja existente. Registro duplicado bloqueado."
        )

    pedido = obter_pedido(numero)
    validacao = validar_pedido(pedido)

    if validacao["pode_analisar_merito"]:
        raise ValueError(
            "Pedido nao exige diligencia preliminar."
        )

    # A matricula original pode estar incorreta.
    # Por isso, a sessao inicial nao recebe identidade pessoal.
    sessao = AgentSession(
        session_id=numero,
        agent_id="agente_diarias",
        user_id=None,
        metadata={
            "numero_pedido": numero,
            "estado": "aguardando_complementacao",
            "eventos_administrativos": [
                criar_evento(
                    "diligencia_preliminar",
                    {
                        "pendencias": validacao["pendencias"],
                        "matricula_informada": str(
                            pedido.get("matricula", "")
                        ),
                    },
                )
            ],
        },
        runs=[],
    )

    resultado = banco.upsert_session(sessao)

    if resultado is None:
        raise RuntimeError(
            "Falha ao persistir diligencia."
        )

    return resultado


def registrar_complementacao(numero):
    """Registra complemento validado na mesma sessao."""
    banco = obter_banco()
    sessao = banco.get_session(numero)

    if sessao is None:
        raise ValueError(
            "Diligencia inicial nao encontrada."
        )

    if sessao.metadata is None:
        sessao.metadata = {}

    eventos = list(
        sessao.metadata.get(
            "eventos_administrativos",
            [],
        )
    )

    if any(
        evento.get("tipo") == "complementacao"
        for evento in eventos
    ):
        raise ValueError(
            "Complementacao ja registrada."
        )

    complemento = aplicar_complementacao(numero)
    pedido = complemento["pedido_corrigido"]
    validacao = validar_pedido(pedido)

    if not validacao["pode_analisar_merito"]:
        raise ValueError(
            "Complementacao nao resolveu as pendencias."
        )

    eventos.append(
        criar_evento(
            "complementacao",
            {
                "matricula_validada": str(
                    pedido["matricula"]
                ),
                "data_retorno": pedido.get(
                    "data_retorno"
                ),
                "pedido_apto_para_analise": True,
            },
        )
    )

    sessao.metadata["eventos_administrativos"] = eventos
    sessao.metadata["estado"] = "complementado"

    # A identidade correta somente e atribuida
    # depois da validacao da complementacao.
    sessao.user_id = str(pedido["matricula"])

    resultado = banco.upsert_session(sessao)

    if resultado is None:
        raise RuntimeError(
            "Falha ao persistir complementacao."
        )

    return resultado
