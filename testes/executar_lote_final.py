"""Lote sequencial final dos 12 pedidos e duas complementacoes.

O modulo nao importa nem inicializa o modelo ate a opcao explicita
``--executar-real``. Resultados individuais e o manifesto sao gravados
atomicamente em uma pasta exclusiva.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Callable
from uuid import uuid4

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from seguranca import sanitizar_texto

PEDIDOS_COMUNS = tuple(f"DIA-2026-{n:04d}" for n in range(101, 111))
PEDIDOS_COMPLEMENTADOS = ("DIA-2026-0111", "DIA-2026-0112")
CASOS_ESPERADOS = tuple(
    [*PEDIDOS_COMUNS]
    + [f"{p}/{fase}" for p in PEDIDOS_COMPLEMENTADOS for fase in ("diligencia_local", "complementacao")]
)

# Tarifa de referencia ja adotada no executor academico de memoria.
TARIFA_USD_POR_MILHAO = {
    "entrada": Decimal("0.20"),
    "entrada_cache": Decimal("0.02"),
    "escrita_cache": Decimal("0.25"),
    "saida": Decimal("1.20"),
}
FONTE_TARIFA = "https://developers.openai.com/api/docs/models/gpt-5.6-luna"


def _json_seguro(valor) -> str:
    return json.dumps(valor, ensure_ascii=False, indent=2, default=str) + "\n"


def _gravar_atomico(caminho: Path, dados) -> None:
    temporario = caminho.with_name(f".{caminho.name}.{uuid4().hex}.tmp")
    try:
        with temporario.open("x", encoding="utf-8", newline="\n") as arquivo:
            arquivo.write(_json_seguro(dados))
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, caminho)
    finally:
        try:
            temporario.unlink()
        except FileNotFoundError:
            pass


def _numero(valor):
    return type(valor) in (int, float) and valor >= 0


def _proteger_evidencia(valor, dados_sensiveis=(), *, campo=None):
    if isinstance(valor, dict):
        return {
            str(chave): (
                "[IDENTIFICADOR_REDACTADO]" if str(chave).casefold() == "matricula"
                else _proteger_evidencia(conteudo, dados_sensiveis, campo=str(chave))
            )
            for chave, conteudo in valor.items()
            if str(chave) not in {"_dados_sensiveis", "run_id", "tool_call_id"}
        }
    if isinstance(valor, (list, tuple)):
        return [_proteger_evidencia(item, dados_sensiveis) for item in valor]
    if isinstance(valor, str):
        texto = sanitizar_texto(valor)
        for sensivel in dados_sensiveis:
            if isinstance(sensivel, str) and sensivel:
                texto = texto.replace(sensivel, "[DADO_PESSOAL_REDACTADO]")
        return texto
    if campo == "matricula" and valor is not None:
        return "[IDENTIFICADOR_REDACTADO]"
    return valor


def _projetar_caso(case_id: str, protocolo: str, etapa: str, resultado: dict) -> dict:
    metricas = resultado.get("metricas")
    if not isinstance(metricas, dict):
        metricas = {}
    modelo_invocado = resultado.get("modelo_invocado", etapa != "diligencia_local") is True
    dados_sensiveis = resultado.get("_dados_sensiveis", ())
    if not isinstance(dados_sensiveis, (list, tuple)):
        dados_sensiveis = ()
    tokens = {}
    for campo in ("input_tokens", "output_tokens", "total_tokens"):
        valor = metricas.get(campo)
        tokens[campo] = valor if modelo_invocado and type(valor) is int and valor >= 0 else None
    tokens_consistentes = (
        tokens["input_tokens"] + tokens["output_tokens"] == tokens["total_tokens"]
        if all(type(tokens[campo]) is int for campo in tokens) else None
    )

    custo = estimar_custo(metricas) if modelo_invocado else None
    duracao = resultado.get("duracao_segundos")
    registro = {
        "caso": case_id,
        "protocolo": protocolo,
        "etapa": etapa,
        "status": resultado.get("status", "desconhecido"),
        "tipo_execucao": resultado.get("tipo_execucao"),
        "modelo_invocado": modelo_invocado,
        "metricas_tokens_status": "observadas" if modelo_invocado and all(v is not None for v in tokens.values()) else (
            "nao_aplicavel" if not modelo_invocado else "indisponiveis"
        ),
        "session_id": protocolo,
        "titular_validado": (
            resultado.get("status") == "conferida"
            and resultado.get("tipo_execucao") != "diligencia_preliminar"
        ),
        **tokens,
        "tokens_consistentes": tokens_consistentes,
        "duracao_segundos": round(duracao, 6) if _numero(duracao) else None,
        "duracao_run_agno_segundos": metricas.get("duracao_run_agno_segundos"),
        "time_to_first_token": metricas.get("time_to_first_token"),
        "cache_read_tokens": metricas.get("cache_read_tokens"),
        "cache_write_tokens": metricas.get("cache_write_tokens"),
        "reasoning_tokens": metricas.get("reasoning_tokens"),
        "custo_estimado_usd": str(custo.quantize(Decimal("0.00000001"))) if custo is not None else None,
        "custo_estimativa_metodo": (
            _metodo_estimativa(metricas) if custo is not None
            else "indisponivel_sem_tokens" if modelo_invocado
            else "nao_aplicavel"
        ),
        "custo_faturado_usd": None,
        "barreira": "aprovada" if resultado.get("status") == "conferida" else "nao_aprovada",
        "falha_tecnica": resultado.get("falha_tecnica") is True,
        "resultado_barreira": _proteger_evidencia(resultado.get("resultado_barreira"), dados_sensiveis),
        "instrucao_conferida": _proteger_evidencia(resultado.get("instrucao_conferida"), dados_sensiveis),
        "consultas": _proteger_evidencia(resultado.get("consultas"), dados_sensiveis),
        "auditoria_ferramentas": _proteger_evidencia(resultado.get("auditoria_ferramentas"), dados_sensiveis),
        "revisao_humana_obrigatoria": resultado.get("revisao_humana_obrigatoria", True),
        "correcao_validada": resultado.get("correcao_validada"),
        "sessao_original_preservada": resultado.get("sessao_original_preservada"),
        "titular_corrigido_utilizado": resultado.get("titular_corrigido_utilizado"),
    }
    if resultado.get("duracao_fluxo_complementacao_segundos") is not None:
        registro["duracao_fluxo_complementacao_segundos"] = resultado["duracao_fluxo_complementacao_segundos"]
    return registro


def _metodo_estimativa(metricas: dict) -> str:
    conhecidos = sum(
        type(metricas.get(campo)) is int and metricas[campo] >= 0
        for campo in ("cache_read_tokens", "cache_write_tokens")
    )
    if conhecidos == 2:
        return "tarifa_com_decomposicao_de_cache"
    if conhecidos == 1:
        return "tarifa_com_decomposicao_parcial_de_cache"
    return "tarifa_de_entrada_sem_decomposicao_de_cache"


def estimar_custo(metricas: dict) -> Decimal | None:
    """Estima por tarifa declarada; sem cache, estima toda entrada pela tarifa normal."""
    entrada, saida = metricas.get("input_tokens"), metricas.get("output_tokens")
    if type(entrada) is not int or entrada < 0 or type(saida) is not int or saida < 0:
        return None
    cache_lido = metricas.get("cache_read_tokens")
    cache_escrito = metricas.get("cache_write_tokens")
    cache_lido = cache_lido if type(cache_lido) is int and cache_lido >= 0 else 0
    cache_escrito = cache_escrito if type(cache_escrito) is int and cache_escrito >= 0 else 0
    if not _numero(cache_lido) or not _numero(cache_escrito):
        return None
    if cache_lido + cache_escrito > entrada:
        return None
    uncached = Decimal(entrada - cache_lido - cache_escrito)
    valor = (
        uncached * TARIFA_USD_POR_MILHAO["entrada"]
        + Decimal(cache_lido) * TARIFA_USD_POR_MILHAO["entrada_cache"]
        + Decimal(cache_escrito) * TARIFA_USD_POR_MILHAO["escrita_cache"]
        + Decimal(saida) * TARIFA_USD_POR_MILHAO["saida"]
    ) / Decimal(1_000_000)
    return valor


def _desativar_retentativas_automaticas(agente) -> None:
    """Desativa retries do Agno, do guidance loop e do cliente OpenAI."""
    modelo = getattr(agente, "model", None)
    if modelo is None:
        raise RuntimeError("modelo_indisponivel")
    modelo.retries = 0
    modelo.retry_with_guidance = False
    modelo.max_retries = 0


def _anotar_disponibilidade_cache(metricas, response_usage):
    entrada = getattr(response_usage, "input_tokens_details", None)
    saida = getattr(response_usage, "output_tokens_details", None)
    def reportado(objeto, campo):
        if isinstance(objeto, dict):
            return campo in objeto
        campos_fornecidos = getattr(objeto, "model_fields_set", None)
        if campos_fornecidos is None:
            campos_fornecidos = getattr(objeto, "__fields_set__", None)
        if campos_fornecidos is not None:
            return campo in campos_fornecidos
        valor = getattr(objeto, campo, None)
        return type(valor) is int and valor > 0

    metricas.provider_metrics = {
        "openai_usage_responses": 1,
        "openai_cache_read_reports": int(
            entrada is not None
            and reportado(entrada, "cached_tokens")
            and type(getattr(entrada, "cached_tokens", None)) is int
            and getattr(entrada, "cached_tokens") >= 0
        ),
        "openai_cache_write_reports": int(
            entrada is not None
            and reportado(entrada, "cache_write_tokens")
            and type(getattr(entrada, "cache_write_tokens", None)) is int
            and getattr(entrada, "cache_write_tokens") >= 0
        ),
        "openai_reasoning_reports": int(
            saida is not None
            and reportado(saida, "reasoning_tokens")
            and type(getattr(saida, "reasoning_tokens", None)) is int
            and getattr(saida, "reasoning_tokens") >= 0
        ),
    }
    return metricas


def _executar_tentativa_real(**kwargs) -> dict:
    """Executa via servico existente com transporte TLS e sem retries."""
    import ssl
    import httpx
    from openai import OpenAI
    from agno.models.openai import OpenAIResponses
    from unittest.mock import patch

    import agente
    from execucao_interativa import _criar_agente_do_servico, executar_tentativa

    _criar_agente_do_servico.cache_clear()
    criar_original = agente.criar_agente_reutilizavel

    with httpx.Client(
        verify=ssl.create_default_context(),
        timeout=40.0,
        follow_redirects=False,
    ) as http:
        cliente = OpenAI(max_retries=0, http_client=http)

        class ModeloComTransporte(OpenAIResponses):
            def get_client(self):
                return cliente

            def _get_metrics(self, response_usage):
                metricas = super()._get_metrics(response_usage)
                return _anotar_disponibilidade_cache(metricas, response_usage)

        def criar_configurado(*args, **opcoes):
            instancia = criar_original(*args, **opcoes)
            modelo_original = instancia.model
            _desativar_retentativas_automaticas(instancia)

            instancia.model = ModeloComTransporte(
                id=modelo_original.id,
                reasoning_effort=modelo_original.reasoning_effort,
                parallel_tool_calls=modelo_original.parallel_tool_calls,
                retries=0,
                retry_with_guidance=False,
                max_retries=0,
            )
            return instancia

        with patch.object(
            agente,
            "criar_agente_reutilizavel",
            side_effect=criar_configurado,
        ):
            return executar_tentativa(**kwargs)


def consolidar(casos: list[dict], *, concluido: bool, duracao_total: float | None) -> dict:
    metricas_modelo = [c for c in casos if c["modelo_invocado"] is True]
    casos_com_metricas = [
        c for c in metricas_modelo
        if all(type(c.get(campo)) is int for campo in ("input_tokens", "output_tokens", "total_tokens"))
        and c.get("tokens_consistentes") is True
        and c.get("custo_estimado_usd") is not None
    ]
    completos = (
        len(casos) == len(CASOS_ESPERADOS)
        and len(metricas_modelo) == len(PEDIDOS_COMUNS) + len(PEDIDOS_COMPLEMENTADOS)
        and len(casos_com_metricas) == len(metricas_modelo)
        and all(c["status"] == "conferida" for c in casos)
    ) and all(
        all(type(c[campo]) is int for campo in ("input_tokens", "output_tokens", "total_tokens"))
        and c["custo_estimado_usd"] is not None
        and c.get("tokens_consistentes") is True
        for c in metricas_modelo
    )
    resultado = {
        "casos_registrados": len(casos),
        "casos_concluidos": sum(c.get("status") == "conferida" for c in casos),
        "casos_esperados": len(CASOS_ESPERADOS),
        "chamadas_logicas_ao_modelo": len(metricas_modelo),
        "metricas_completas": completos,
        "casos_modelo_com_metricas_completas": len(casos_com_metricas),
        "cache_decomposicao_completa": bool(metricas_modelo) and all(
            type(c.get("cache_read_tokens")) is int and type(c.get("cache_write_tokens")) is int
            for c in metricas_modelo
        ),
        "totais_tokens_consistentes": all(c.get("tokens_consistentes") is True for c in metricas_modelo),
        "input_tokens": sum(c["input_tokens"] for c in metricas_modelo) if completos else None,
        "output_tokens": sum(c["output_tokens"] for c in metricas_modelo) if completos else None,
        "total_tokens": sum(c["total_tokens"] for c in metricas_modelo) if completos else None,
        "subtotal_input_tokens_casos_com_metricas": sum(c["input_tokens"] for c in casos_com_metricas),
        "subtotal_output_tokens_casos_com_metricas": sum(c["output_tokens"] for c in casos_com_metricas),
        "subtotal_total_tokens_casos_com_metricas": sum(c["total_tokens"] for c in casos_com_metricas),
        "cache_read_tokens": (
            sum(c["cache_read_tokens"] for c in metricas_modelo)
            if metricas_modelo and all(type(c.get("cache_read_tokens")) is int for c in metricas_modelo) else None
        ),
        "cache_write_tokens": (
            sum(c["cache_write_tokens"] for c in metricas_modelo)
            if metricas_modelo and all(type(c.get("cache_write_tokens")) is int for c in metricas_modelo) else None
        ),
        "duracao_casos_servico_segundos": round(
            sum(c["duracao_segundos"] for c in casos if _numero(c.get("duracao_segundos"))), 6
        ),
        "diferenca_nao_atribuida_segundos": (
            round(duracao_total - sum(c["duracao_segundos"] for c in casos if _numero(c.get("duracao_segundos"))), 6)
            if duracao_total is not None else None
        ),
        "duracao_total_segundos": round(duracao_total, 6) if duracao_total is not None else None,
        "custo_estimado_usd": (
            str(sum((Decimal(c["custo_estimado_usd"]) for c in metricas_modelo), Decimal(0)).quantize(Decimal("0.00000001")))
            if completos else None
        ),
        "subtotal_custo_estimado_usd_casos_com_metricas": (
            str(sum((Decimal(c["custo_estimado_usd"]) for c in casos_com_metricas), Decimal(0)).quantize(Decimal("0.00000001")))
            if casos_com_metricas else None
        ),
        "custo_faturado_usd": None,
        "estado": "concluido" if concluido else "parcial",
    }
    return resultado


def executar_lote(
    executar_pedido: Callable[[str], dict],
    executar_complementacao: Callable[[str, Callable[[dict], None]], dict],
    *,
    diretorio_saida: Path,
) -> dict:
    """Executa as 14 etapas em ordem, com checkpoint depois de cada etapa.

    ``executar_complementacao`` deve chamar o callback com a diligencia local
    antes de registrar/retomar a complementacao na mesma sessao.
    """
    destino = Path(diretorio_saida)
    destino.mkdir(parents=True, exist_ok=False)
    inicio = perf_counter()
    casos: list[dict] = []
    manifesto = {
        "versao": 2,
        "finalidade": "lote final detalhado dos 12 pedidos e duas complementacoes; nova execucao isolada",
        "inicio_utc": datetime.now(timezone.utc).isoformat(),
        "sequencia_esperada": list(CASOS_ESPERADOS),
        "casos": [],
        "tarifa": {
            "fonte": FONTE_TARIFA,
            "consulta": "2026-11-22",
            "usd_por_milhao": {k: str(v) for k, v in TARIFA_USD_POR_MILHAO.items()},
        },
        "custos_faturados_disponiveis": False,
        "metricas_duracao": {
            "duracao_segundos": "tempo de executar_tentativa por caso; inclui validação e não isola o transporte HTTP",
            "duracao_run_agno_segundos": "duração de run informada pelo Agno, incluindo interação com ferramentas",
            "duracao_total_segundos": "tempo do orquestrador para o lote, incluindo preparação e checkpoints",
            "diferenca_nao_atribuida_segundos": "diferença aritmética, não uma medição autônoma de orquestração",
        },
        "estado": "em_execucao",
    }

    def checkpoint(registro: dict) -> None:
        casos.append(registro)
        _gravar_atomico(destino / f"{len(casos):02d}_{registro['caso'].replace('/', '_')}.json", registro)
        manifesto["casos"] = [c["caso"] for c in casos]
        manifesto["metricas"] = consolidar(casos, concluido=False, duracao_total=perf_counter() - inicio)
        _gravar_atomico(destino / "manifesto.json", manifesto)

    _gravar_atomico(destino / "manifesto.json", manifesto)
    try:
        for protocolo in PEDIDOS_COMUNS:
            inicio_caso = perf_counter()
            try:
                resultado = executar_pedido(protocolo)
            except Exception as erro:
                falha = {
                    "status": "erro", "tipo_execucao": "analise_merito",
                    "metricas": None, "duracao_segundos": perf_counter() - inicio_caso,
                }
                registro = _projetar_caso(protocolo, protocolo, "analise", falha)
                registro["classe_erro"] = type(erro).__name__
                checkpoint(registro)
                raise
            caso = _projetar_caso(protocolo, protocolo, "analise", resultado)
            checkpoint(caso)
            if caso.get("falha_tecnica"):
                raise RuntimeError(f"falha_tecnica:{protocolo}")
            if caso["status"] not in ("conferida", "analise_manual"):
                raise RuntimeError(f"execucao_interrompida:{protocolo}")

        for protocolo in PEDIDOS_COMPLEMENTADOS:
            local_salvo = False

            def registrar_local(resultado_local: dict) -> None:
                nonlocal local_salvo
                caso_local = _projetar_caso(
                    f"{protocolo}/diligencia_local", protocolo, "diligencia_local", resultado_local,
                )
                checkpoint(caso_local)
                local_salvo = True
                if caso_local["status"] != "conferida":
                    raise RuntimeError(f"diligencia_interrompida:{protocolo}")

            try:
                resultado = executar_complementacao(protocolo, registrar_local)
            except Exception as erro:
                if not local_salvo:
                    checkpoint(_projetar_caso(
                        f"{protocolo}/diligencia_local", protocolo, "diligencia_local",
                        {"status": "erro", "tipo_execucao": "diligencia_preliminar", "duracao_segundos": None},
                    ))
                falha = {
                    "caso": f"{protocolo}/complementacao",
                    "protocolo": protocolo,
                    "etapa": "complementacao",
                    "status": "erro",
                    "classe_erro": type(erro).__name__,
                    "session_id": protocolo,
                    "modelo_invocado": None,
                    "input_tokens": None,
                    "output_tokens": None,
                    "total_tokens": None,
                    "duracao_segundos": None,
                    "custo_estimado_usd": None,
                    "custo_faturado_usd": None,
                    "barreira": "nao_aprovada",
                }
                checkpoint(falha)
                raise
            caso = _projetar_caso(
                f"{protocolo}/complementacao", protocolo, "complementacao", resultado,
            )
            checkpoint(caso)
            if caso.get("falha_tecnica"):
                raise RuntimeError(f"falha_tecnica:{protocolo}")
            if caso["status"] != "conferida":
                raise RuntimeError(f"complementacao_interrompida:{protocolo}")
    except Exception as erro:
        manifesto["estado"] = "interrompido"
        manifesto["erro"] = type(erro).__name__
        manifesto["metricas"] = consolidar(casos, concluido=False, duracao_total=perf_counter() - inicio)
        _gravar_atomico(destino / "manifesto.json", manifesto)
        return manifesto

    manifesto["estado"] = "concluido"
    manifesto["fim_utc"] = datetime.now(timezone.utc).isoformat()
    manifesto["metricas"] = consolidar(casos, concluido=True, duracao_total=perf_counter() - inicio)
    _gravar_atomico(destino / "manifesto.json", manifesto)
    return manifesto


def _executar_pedido_real(protocolo: str) -> dict:
    from uuid import uuid4

    from agente import obter_pedido
    pedido = obter_pedido(protocolo)
    resultado = _executar_tentativa_real(
        protocolo=protocolo,
        tentativa_id=str(uuid4()),
        pedido=pedido,
        session_id=protocolo,
        user_id=str(pedido["matricula"]),
    )
    resultado["_dados_sensiveis"] = [pedido.get("matricula"), pedido.get("nome")]
    return resultado


def _executar_complementacao_real(protocolo: str, registrar_local: Callable[[dict], None]) -> dict:
    from uuid import uuid4

    from barreira_persistente import BarreiraPersistente
    from complementacoes import CAMPOS_COMPLEMENTAVEIS, aplicar_complementacao
    from persistencia_sessoes import preparar_pedido_complementado, registrar_complementacao, registrar_diligencia

    inicio = perf_counter()
    complemento = aplicar_complementacao(protocolo)
    original, corrigido = complemento["pedido_original"], complemento["pedido_corrigido"]
    titular = corrigido["matricula"]
    with tempfile.TemporaryDirectory(prefix="lote14-") as pasta:
        caminho = Path(pasta).resolve() / "sessao.db"
        caminho.touch(exist_ok=False)
        autorizado = caminho
        barreira = BarreiraPersistente(secrets.token_bytes(32))
        barreira.preparar(caminho_banco=caminho, banco_autorizado=autorizado)
        barreira.vincular_protocolo_validado(protocolo, titular, caminho_banco=caminho, banco_autorizado=autorizado)

        diligencia = _executar_tentativa_real(
            protocolo=protocolo, tentativa_id=str(uuid4()), pedido=original,
            session_id=protocolo, user_id=None,
        )
        dados_sensiveis = sorted({
            str(valor)
            for pedido_privado in (original, corrigido)
            for valor in (pedido_privado.get("matricula"), pedido_privado.get("nome"))
            if isinstance(valor, str) and valor
        })
        diligencia["_dados_sensiveis"] = dados_sensiveis
        registrar_local(diligencia)

        if diligencia.get("status") != "conferida":
            raise RuntimeError("diligencia_local_nao_conferida")

        with barreira.abrir_agno(titular, caminho_banco=caminho, banco_autorizado=autorizado) as banco:
            sessao = registrar_diligencia(
                protocolo, caminho_banco=caminho, banco_protegido=banco,
            )
            if sessao.session_id != protocolo or sessao.user_id is not None:
                raise RuntimeError("sessao_inicial_incompativel")
            campo = CAMPOS_COMPLEMENTAVEIS[protocolo]
            registrar_complementacao(
                protocolo, {campo: corrigido[campo]}, caminho_banco=caminho, banco_protegido=banco,
            )

        preparado = preparar_pedido_complementado(protocolo, caminho_banco=caminho)
        if (
            preparado["pedido_corrigido"] != corrigido
            or preparado["session_id"] != protocolo
            or preparado["user_id"] != titular
        ):
            raise RuntimeError("complementacao_persistida_incompativel")
        retorno = _executar_tentativa_real(
            protocolo=protocolo, tentativa_id=str(uuid4()), pedido=preparado["pedido_corrigido"],
            session_id=preparado["session_id"], user_id=preparado["user_id"],
            usar_memoria=True, caminho_banco=caminho, barreira_persistente=barreira,
            banco_autorizado=autorizado,
        )
        # A projeção da evidência não contém matrícula, nome ou conteúdo bruto.
        retorno["correcao_validada"] = True
        retorno["sessao_original_preservada"] = True
        retorno["titular_corrigido_utilizado"] = True
        retorno["duracao_fluxo_complementacao_segundos"] = perf_counter() - inicio
        retorno["_dados_sensiveis"] = dados_sensiveis
        return retorno


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Executor sequencial, auditavel, dos 14 casos finais.")
    parser.add_argument("--executar-real", action="store_true", help="Autoriza chamadas reais ao modelo para o lote completo.")
    args = parser.parse_args(argv)
    if not args.executar_real:
        parser.error("operacao real exige --executar-real; nenhum caso foi iniciado")
    raiz = BASE / "resultados"
    destino = raiz / f"lote_final_14_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    try:
        manifesto = executar_lote(_executar_pedido_real, _executar_complementacao_real, diretorio_saida=destino)
    except FileExistsError:
        print("Pasta de resultados ja existe; nenhuma execucao iniciada.", file=sys.stderr)
        return 2
    print(f"Estado: {manifesto['estado']}")
    print(f"Resultados: {destino}")
    print(_json_seguro(manifesto["metricas"]))
    return 0 if manifesto["estado"] == "concluido" else 1


if __name__ == "__main__":
    raise SystemExit(main())
