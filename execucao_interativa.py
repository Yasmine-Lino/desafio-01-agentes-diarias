"""Executa exclusivamente tentativas submetidas pelo chamador."""

import re
from contextlib import contextmanager
from copy import deepcopy
from datetime import date
from functools import lru_cache
from math import isfinite
from pathlib import Path
from threading import Lock
from time import perf_counter

from agno.run.agent import RunOutput, RunStatus

from auditoria_execucao import registrar_ferramentas
from barreira_persistente import exige_admissao
from barreira_validacao import validar_instrucao
from complementacoes import CAMPOS_COMPLEMENTAVEIS
from diligencia_preliminar import criar_instrucao_diligencia
from modelos import Instrucao
from seguranca import sanitizar_texto
from validacao_pedido import validar_pedido


_PROTOCOLO = re.compile(r"DIA-[0-9]{4}-[0-9]{4}")
_TENTATIVA = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
_MATRICULA = re.compile(r"[0-9]{6}")
_BANCO_OFICIAL = Path(__file__).resolve().parent / "resultados" / "agente_sessoes.db"
_MENSAGEM_MANUAL = (
    "Instrucao indisponivel para revisao automatizada. "
    "Encaminhe o pedido para analise manual."
)
_BLOQUEIO_TENTATIVAS = Lock()
_TENTATIVAS_USADAS: set[str] = set()
_BLOQUEIO_AGENTES = Lock()


@lru_cache(maxsize=4)
def _criar_agente_do_servico(caminho_banco):
    # O modulo do agente configura o provedor, apenas no caminho de merito.
    from agente import criar_agente_reutilizavel

    return criar_agente_reutilizavel(
        usar_memoria=caminho_banco is not None,
        caminho_banco=caminho_banco,
    )


@contextmanager
def _agente_da_tentativa(caminho_banco, matricula, barreira_persistente, banco_autorizado):
    if barreira_persistente is None:
        if exige_admissao(caminho_banco):
            raise PermissionError("Admissao obrigatoria no banco protegido.")
        with _BLOQUEIO_AGENTES:
            agente = _criar_agente_do_servico(caminho_banco)
        yield agente
        return

    with barreira_persistente.abrir_agno(
        matricula, caminho_banco=caminho_banco, banco_autorizado=banco_autorizado,
    ) as banco:
        from agente import criar_agente_reutilizavel

        yield criar_agente_reutilizavel(
            usar_memoria=True, caminho_banco=caminho_banco, banco_protegido=banco,
        )
        barreira_persistente.confirmar_admissao(banco, matricula)


def _reservar_tentativa(tentativa_id):
    with _BLOQUEIO_TENTATIVAS:
        if tentativa_id in _TENTATIVAS_USADAS:
            return False
        _TENTATIVAS_USADAS.add(tentativa_id)
        return True


def _matricula(valor):
    if isinstance(valor, str) and _MATRICULA.fullmatch(valor.strip()):
        return valor.strip()
    return None


def _caminho_memoria(usar_memoria, caminho_banco):
    if usar_memoria is False and caminho_banco is None:
        return None
    if usar_memoria is not True or caminho_banco is None:
        raise ValueError("Configuracao de memoria invalida.")
    caminho = Path(caminho_banco).resolve()
    # O banco oficial fica fora do escopo deste servico.
    if caminho == _BANCO_OFICIAL.resolve():
        raise ValueError("Banco nao habilitado para o servico.")
    return caminho


def _validar_dados_merito(pedido):
    datas = []
    for campo in ("data_pedido", "data_partida", "data_retorno"):
        valor = pedido.get(campo)
        if not isinstance(valor, str):
            raise ValueError("Data operacional invalida.")
        data = date.fromisoformat(valor)
        if data.isoformat() != valor:
            raise ValueError("Data operacional invalida.")
        datas.append(data)

    protocolo, partida, retorno = datas
    if not protocolo <= partida <= retorno:
        raise ValueError("Datas operacionais incoerentes.")
    uf = pedido.get("destino_uf")
    if not isinstance(uf, str) or re.fullmatch(r"[A-Z]{2}", uf.strip().upper()) is None:
        raise ValueError("UF operacional invalida.")
    for campo in ("nome", "destino_municipio", "transporte"):
        valor = pedido.get(campo)
        if not isinstance(valor, str) or not valor.strip() or sanitizar_texto(valor) != valor:
            raise ValueError("Campo operacional invalido.")
    if not isinstance(pedido.get("justificativa"), str):
        raise ValueError("Justificativa operacional invalida.")


def _metricas_observadas(metricas):
    if metricas is None:
        return None
    tokens = {}
    for campo in ("input_tokens", "output_tokens", "total_tokens"):
        valor = getattr(metricas, campo, None)
        if type(valor) is int and valor >= 0:
            tokens[campo] = valor

    # Agno agrega campos de cache ausentes como zero. Só os publica quando
    # o adaptador observou os campos correspondentes em todas as respostas.
    detalhes = getattr(metricas, "details", None)
    modelos = [
        modelo
        for grupo in (detalhes or {}).values()
        for modelo in (grupo or ())
    ] if isinstance(detalhes, dict) else []
    metricas_provedor = [
        getattr(modelo, "provider_metrics", None)
        for modelo in modelos
        if isinstance(getattr(modelo, "provider_metrics", None), dict)
    ]
    respostas = sum(
        valor.get("openai_usage_responses", 0)
        for valor in metricas_provedor
        if type(valor.get("openai_usage_responses")) is int
    )
    observadas = {}
    if any(tokens.values()) or respostas:
        observadas.update(tokens)
    if respostas and sum(
        valor.get("openai_cache_read_reports", 0)
        for valor in metricas_provedor
        if type(valor.get("openai_cache_read_reports")) is int
    ) == respostas:
        valor = getattr(metricas, "cache_read_tokens", None)
        if type(valor) is int and valor >= 0:
            observadas["cache_read_tokens"] = valor
    if respostas and sum(
        valor.get("openai_cache_write_reports", 0)
        for valor in metricas_provedor
        if type(valor.get("openai_cache_write_reports")) is int
    ) == respostas:
        valor = getattr(metricas, "cache_write_tokens", None)
        if type(valor) is int and valor >= 0:
            observadas["cache_write_tokens"] = valor
    if respostas and sum(
        valor.get("openai_reasoning_reports", 0)
        for valor in metricas_provedor
        if type(valor.get("openai_reasoning_reports")) is int
    ) == respostas:
        valor = getattr(metricas, "reasoning_tokens", None)
        if type(valor) is int and valor >= 0:
            observadas["reasoning_tokens"] = valor

    for campo in ("cost", "duration", "time_to_first_token"):
        valor = getattr(metricas, campo, None)
        if type(valor) in (int, float) and isfinite(valor) and valor >= 0:
            chave = "duracao_run_agno_segundos" if campo == "duration" else campo
            observadas[chave] = valor
    return observadas or None


def _ler_instrucao(conteudo):
    if isinstance(conteudo, Instrucao):
        conteudo = conteudo.model_dump(mode="python")
    if isinstance(conteudo, str):
        return Instrucao.model_validate_json(conteudo, strict=True)
    return Instrucao.model_validate(conteudo, strict=True)


def _publicar_instrucao(barreira, protocolo, matricula, *, preliminar):
    if (
        barreira.get("aprovado") is not True
        or barreira.get("texto_conferido") is not True
        or barreira.get("numero_pedido") != protocolo
    ):
        raise ValueError("Instrucao nao liberada pela barreira.")

    instrucao = Instrucao.model_validate(barreira.get("instrucao_conferida"), strict=True)
    if instrucao.numero_pedido != protocolo or instrucao.matricula != matricula:
        raise ValueError("Instrucao conferida sem vinculo com o pedido.")

    if preliminar and (
        instrucao.recomendacao != "diligencia"
        or instrucao.quantidade_diarias is not None
        or instrucao.valor_total is not None
        or instrucao.exige_autorizacao_superior
    ):
        raise ValueError("Instrucao preliminar invalida.")

    textos = (
        instrucao.minuta_despacho, *instrucao.pendencias, *instrucao.alertas,
        *(item.detalhe for item in instrucao.verificacoes),
    )
    if any(not texto.strip() or sanitizar_texto(texto) != texto for texto in textos):
        raise ValueError("Instrucao conferida indisponivel para publicacao.")
    return instrucao.model_dump(mode="json")


_ARGUMENTOS_PUBLICOS = {
    ("verificar_cadastro", "consultar_servidor"): ("matricula",),
    ("verificar_prestacoes", "consultar_historico"): ("matricula", "mes_referencia", "data_analise"),
    ("verificar_calculo", "calcular_diarias"): (
        "matricula", "destino_uf", "data_pedido", "data_partida", "data_retorno", "mes_referencia", "data_analise",
    ),
    ("verificar_orcamento", "consultar_saldo"): ("matricula", "valor_solicitado"),
}
_ARGUMENTOS_PUBLICOS["verificar_orcamento", "calcular_diarias"] = _ARGUMENTOS_PUBLICOS[
    "verificar_calculo", "calcular_diarias"
]


def consultas_publicaveis(auditoria, matricula):
    """Projeta somente argumentos operacionais da trilha Python já conferida."""
    consultas = []
    for chamada in auditoria.get("chamadas_python", ()):
        if not isinstance(chamada, dict) or chamada.get("erro") is not False:
            continue
        ferramenta, nome = chamada.get("ferramenta_agno"), chamada.get("nome")
        if not isinstance(ferramenta, str) or not isinstance(nome, str):
            continue
        campos = _ARGUMENTOS_PUBLICOS.get((ferramenta, nome))
        dados = chamada.get("argumentos")
        if campos is None or not isinstance(dados, dict) or dados.get("matricula") != matricula:
            continue
        argumentos = {}
        for campo in campos:
            valor = dados.get(campo)
            if campo == "valor_solicitado":
                if type(valor) in (int, float) and isfinite(valor) and valor > 0:
                    argumentos[campo] = valor
                continue
            padrao = {
                "matricula": r"[0-9]{6}", "destino_uf": r"[A-Za-z]{2}",
                "mes_referencia": r"[0-9]{4}-[0-9]{2}",
            }.get(campo, r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
            if isinstance(valor, str) and re.fullmatch(padrao, valor):
                argumentos[campo] = valor
        if len(argumentos) == len(campos):
            consultas.append({"ferramenta_agno": ferramenta, "nome": nome, "argumentos": argumentos, "erro": False})
    return consultas


def _auditoria_publicable(auditoria):
    """Projeta chamadas verificadas sem identificadores ou conteúdo livre."""
    chamadas = []
    for chamada in auditoria.get("chamadas", ()):
        if not isinstance(chamada, dict):
            continue
        argumentos = chamada.get("argumentos", {})
        resultado = chamada.get("resultado", {})
        metricas = chamada.get("metricas", {})
        chamadas.append({
            "nome": chamada.get("nome"),
            "argumentos": {
                chave: ("[IDENTIFICADOR_REDACTADO]" if chave == "matricula" else valor)
                for chave, valor in argumentos.items()
            } if isinstance(argumentos, dict) else {},
            "resultado": {
                chave: ("[IDENTIFICADOR_REDACTADO]" if chave == "matricula" else valor)
                for chave, valor in resultado.items()
            } if isinstance(resultado, dict) else {},
            "erro": chamada.get("erro") is True,
            "metricas": {
                chave: valor for chave, valor in metricas.items()
                if chave in ("time", "duration", "duration_seconds")
                and type(valor) in (int, float) and isfinite(valor) and valor >= 0
            } if isinstance(metricas, dict) else {},
        })
    return {
        "total_chamadas": len(chamadas),
        "estado_trilha": auditoria.get("estado_trilha"),
        "estado_contexto": auditoria.get("estado_contexto"),
        "chamadas": chamadas,
    }


def executar_tentativa(
    *,
    protocolo: str,
    tentativa_id: str,
    pedido: dict,
    session_id: str,
    user_id: str | None,
    usar_memoria: bool = False,
    caminho_banco: str | Path | None = None,
    barreira_persistente=None,
    banco_autorizado: Path | None = None,
) -> dict:
    """Executa uma tentativa UUID. Na diligencia preliminar, user_id deve ser nulo.

    O pedido corrigido deve vir do fluxo administrativo validado. Este servico
    nao aplica complementacoes nem registra eventos administrativos.
    """
    inicio = perf_counter()
    tentativa_valida = isinstance(tentativa_id, str) and _TENTATIVA.fullmatch(tentativa_id)
    protocolo_valido = isinstance(protocolo, str) and _PROTOCOLO.fullmatch(protocolo)
    resultado = {
        "tentativa_id": tentativa_id if tentativa_valida else None,
        "protocolo": protocolo if protocolo_valido else None,
        "status": "analise_manual",
        "mensagem": _MENSAGEM_MANUAL,
        "metricas": None,
        "modelo_invocado": False,
        "revisao_humana_obrigatoria": True,
    }

    try:
        if not tentativa_valida or not _reservar_tentativa(tentativa_id):
            raise ValueError("Tentativa invalida ou ja utilizada.")
        if not protocolo_valido or session_id != protocolo or not isinstance(pedido, dict):
            raise ValueError("Identificacao do pedido invalida.")
        dados = deepcopy(pedido)
        matricula = _matricula(dados.get("matricula"))
        if dados.get("numero") != protocolo or matricula is None:
            raise ValueError("Pedido sem identidade operacional valida.")

        validacao = validar_pedido(dados)
        preliminar = not validacao["pode_analisar_merito"]
        if preliminar:
            if user_id is not None:
                raise ValueError("Diligencia preliminar nao admite titular vinculado.")
            instrucao = criar_instrucao_diligencia(dados)
            auditoria = {"chamadas": []}
        else:
            if _matricula(user_id) != matricula:
                raise ValueError("Titular divergente do pedido.")
            _validar_dados_merito(dados)
            banco = _caminho_memoria(usar_memoria, caminho_banco)
            with _agente_da_tentativa(banco, matricula, barreira_persistente, banco_autorizado) as agente:
                resultado["modelo_invocado"] = True
                resposta = agente.run(
                    pedido=dados, session_id=session_id, user_id=matricula, run_id=tentativa_id,
                    retomar_complementacao=banco is not None and protocolo in CAMPOS_COMPLEMENTAVEIS,
                )
            if not isinstance(resposta, RunOutput):
                raise ValueError("Resposta inesperada do agente.")
            if (resposta.run_id, resposta.session_id, resposta.user_id) != (
                tentativa_id, session_id, matricula
            ):
                raise ValueError("Resposta de outra execucao.")
            resultado["metricas"] = _metricas_observadas(resposta.metrics)
            if resposta.status is not RunStatus.completed:
                raise ValueError("Execucao nao concluida.")
            instrucao = _ler_instrucao(resposta.content)
            auditoria = registrar_ferramentas(resposta)
            contexto = auditoria.get("contexto_execucao")
            if (
                auditoria.get("estado_contexto") != "completo"
                or auditoria.get("estado_trilha") != "completa"
                or not isinstance(contexto, dict)
                or (contexto.get("run_id"), contexto.get("session_id"), contexto.get("user_id"))
                != (tentativa_id, session_id, matricula)
            ):
                raise ValueError("Auditoria sem vinculo com a tentativa.")

        barreira = validar_instrucao(dados, instrucao, auditoria)
        conferida = _publicar_instrucao(barreira, protocolo, matricula, preliminar=preliminar)
        resultado.update(
            status="conferida",
            tipo_execucao="diligencia_preliminar" if preliminar else "analise_merito",
            instrucao_conferida=conferida,
            consultas=consultas_publicaveis(auditoria, matricula),
            resultado_barreira={
                "aprovado": barreira.get("aprovado") is True,
                "texto_conferido": barreira.get("texto_conferido") is True,
                "quantidade_erros": len(barreira.get("erros", ()))
                if isinstance(barreira.get("erros"), list) else None,
                "erros": barreira.get("erros", []),
                "recomendacao_conferida": conferida.get("recomendacao"),
                "criterios_verificados": conferida.get("verificacoes", []),
                "quantidade_diarias_conferida": conferida.get("quantidade_diarias"),
                "valor_total_conferido": conferida.get("valor_total"),
                "exige_autorizacao_superior": conferida.get("exige_autorizacao_superior"),
            },
        )
        if not preliminar:
            resultado["auditoria_ferramentas"] = _auditoria_publicable(auditoria)
        resultado.pop("mensagem")
        if not preliminar:
            resultado["run_id"] = tentativa_id
    except Exception:
        # Fronteira da interface: textos de erro e conteudo recusado ficam fora do retorno.
        resultado["falha_tecnica"] = True
    resultado["duracao_segundos"] = perf_counter() - inicio
    return resultado
