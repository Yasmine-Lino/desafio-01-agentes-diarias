"""Experimento acadêmico de Yasmine Lino Franco para as complementações 0111 e 0112."""

import json
import os
import re
import secrets
import ssl
import sys
from collections import Counter
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from contextvars import ContextVar
from datetime import datetime, timezone
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from time import perf_counter
from uuid import uuid4

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

PEDIDOS = ("DIA-2026-0111", "DIA-2026-0112")
MODOS = {"A": (False, False), "B": (True, False), "C": (True, True)}
MODELO = "gpt-5.6-luna"
SAIDA = BASE / "resultados" / "experimentos_memoria_0111_0112"
FONTE_TARIFA = "https://developers.openai.com/api/docs/models/gpt-5.6-luna"
TARIFA = {
    "fonte": FONTE_TARIFA, "consulta": "2026-11-22", "moeda": "USD",
    "por_milhao": {"entrada": "0.20", "entrada_cache": "0.02", "saida": "1.20"},
}
_TOKENS = ("input_tokens", "output_tokens", "total_tokens")


def _quantidade(valor):
    return valor if type(valor) is int and valor >= 0 else None


def estimar_custo(chamadas):
    if not chamadas or any(not evento.get("metricas") for evento in chamadas):
        return None
    total = Decimal(0)
    for evento in chamadas:
        uso = evento["metricas"]
        entrada, saida, cache = (uso.get(chave) for chave in ("input_tokens", "output_tokens", "cached_tokens"))
        if None in (entrada, saida, cache) or cache > entrada or entrada > 272_000:
            return None
        escrita = uso.get("cache_write_tokens")
        if escrita is not None and escrita > entrada - cache:
            return None
        escrita = escrita or 0
        total += (entrada - cache - escrita) * Decimal("0.20") + cache * Decimal("0.02")
        total += escrita * Decimal("0.25") + saida * Decimal("1.20")
    return str((total / 1_000_000).quantize(Decimal("0.00000001")))


class Medicao:
    """Captura argumentos de invoke e métricas HTTP sem exportar mensagens brutas."""

    def __init__(self, preparado, matricula_divergente):
        self.preparado = preparado
        self.matricula_divergente = matricula_divergente
        self.atual = ContextVar("chamada", default=None)
        self.evento_atual = ContextVar("evento_http", default=None)
        self.requisicoes = []
        self.contextos = []
        self.falhas = []
        self.lock = Lock()
        self.interromper = False

    def _conferir_privacidade(self, texto):
        from seguranca import sanitizar_texto

        if sanitizar_texto(texto) != texto:
            raise ValueError("dados_sensiveis_detectados")
        if self.matricula_divergente and re.search(
            rf"(?<![0-9]){re.escape(self.matricula_divergente)}(?![0-9])", texto,
        ):
            raise ValueError("matricula_divergente_no_contexto")

    def capturar(self, messages, run_response):
        textos = [m.get_content_string() for m in messages]
        for texto in textos:
            self._conferir_privacidade(texto)
        papel = "analise" if run_response is not None else "memoria_pessoal"
        captura = {
            "finalidade": papel, "papeis": dict(Counter(m.role for m in messages)),
            "mensagens_de_replay": sum(bool(m.from_history) for m in messages),
            "memoria_pessoal_no_sistema": any(
                "<memories_from_previous_interactions>" in texto
                for m, texto in zip(messages, textos) if m.role == "system"
            ),
        }
        if papel == "analise":
            atual = json.loads(next(
                texto for m, texto in reversed(list(zip(messages, textos))) if m.role == "user" and not m.from_history
            ))
            esperado = self.preparado["pedido_corrigido"]
            campos = ("numero", "matricula", "data_pedido", "data_partida", "data_retorno")
            if (
                any(atual.get(campo) != esperado[campo] for campo in campos)
                or atual.get("resumo_administrativo") != self.preparado["resumo_administrativo"]
                or (run_response.session_id, run_response.user_id) !=
                (self.preparado["session_id"], self.preparado["user_id"])
            ):
                raise ValueError("contexto_incompativel")
            captura.update(
                entrada_operacional={campo: atual[campo] for campo in campos},
                resumo_administrativo=atual["resumo_administrativo"],
                justificativa_presente="justificativa" in atual,
            )
        with self.lock:
            self.contextos.append(captura)
        return captura

    def antes_requisicao(self, requisicao):
        captura = self.atual.get()
        if (
            captura is None or requisicao.method != "POST" or requisicao.url.scheme != "https"
            or requisicao.url.host != "api.openai.com" or requisicao.url.path != "/v1/responses"
        ):
            raise ValueError("endpoint_ou_chamada_nao_autorizada")
        corpo = json.loads(requisicao.content)
        if corpo.get("model") != MODELO:
            raise ValueError("modelo_nao_autorizado")
        itens = corpo.get("input")
        entrada = json.dumps(itens, ensure_ascii=False)
        # IDs do protocolo podem conter sequências iguais a CPF. A projeção
        # para inspeção preserva argumentos, resultados e textos integralmente.
        if isinstance(itens, list):
            itens_inspecionados = []
            for item in itens:
                if isinstance(item, dict) and item.get("type") in ("function_call", "function_call_output"):
                    item = item.copy()
                    campos_ids = {"call_id": "call"}
                    if item["type"] == "function_call":
                        campos_ids["id"] = "fc"
                    for campo, prefixo in campos_ids.items():
                        valor = item.get(campo)
                        if isinstance(valor, str) and re.fullmatch(rf"{prefixo}_[a-zA-Z0-9]{{16,}}", valor):
                            item[campo] = re.sub(r"(?<!\d)\d{11}(?!\d)", "id", valor)
                itens_inspecionados.append(item)
            self._conferir_privacidade(json.dumps(itens_inspecionados, ensure_ascii=False))
        else:
            self._conferir_privacidade(entrada)
        if captura["finalidade"] == "analise" and not all(
            valor in entrada for valor in captura["entrada_operacional"].values()
        ):
            raise ValueError("payload_sem_contexto_verificado")
        with self.lock:
            if self.interromper:
                raise ValueError("cenario_interrompido")
            evento = {"finalidade": captura["finalidade"], "http_status": None, "metricas": None}
            self.requisicoes.append(evento)
            self.evento_atual.set(evento)
            requisicao.extensions["experimento_evento"] = evento
            captura["payload_verificado"] = True

    def depois_resposta(self, resposta):
        evento = resposta.request.extensions["experimento_evento"]
        with self.lock:
            evento["http_status"] = resposta.status_code
            if not resposta.is_success:
                self.interromper = True
                return
        resposta.read()
        uso = resposta.json().get("usage")
        if isinstance(uso, dict):
            detalhe = uso.get("input_tokens_details") or {}
            evento["metricas"] = {
                **{campo: _quantidade(uso.get(campo)) for campo in _TOKENS},
                "cached_tokens": _quantidade(detalhe.get("cached_tokens")),
                "cache_write_tokens": _quantidade(detalhe.get("cache_write_tokens")),
            }

    @contextmanager
    def observar_falha(self):
        token = self.evento_atual.set(None)
        inicio = perf_counter()
        try:
            yield
        except Exception as erro:
            evento = self.evento_atual.get()
            falha = _classificar_falha(erro, evento)
            with self.lock:
                self.interromper = True
                self.falhas.append({
                    **falha, "segundos": round(perf_counter() - inicio, 6),
                    "tentativas": int(evento is not None),
                })
            raise
        finally:
            self.evento_atual.reset(token)

    def acumular(self, turno):
        chamadas = self.requisicoes
        turno.update(
            chamadas_ao_modelo=len(chamadas),
            chamadas_por_finalidade=dict(Counter(e["finalidade"] for e in chamadas)),
            requisicoes=chamadas,
            contexto=self.contextos,
            falhas_no_modelo=self.falhas,
            custo_estimado_usd=estimar_custo(chamadas), custo_faturado_usd=None,
        )
        for campo in _TOKENS:
            valores = [(e.get("metricas") or {}).get(campo) for e in chamadas]
            turno[campo] = sum(valores) if valores and None not in valores else None
        turno["situacao_custo"] = "estimado" if turno["custo_estimado_usd"] is not None else "nao_disponivel"


def _novo_turno(tipo):
    return {
        "tipo": tipo, "status": "nao_executado", "session_id": None, "user_id": None,
        "chamadas_ao_modelo": 0, **dict.fromkeys(_TOKENS), "segundos": None,
        "recomendacao": None, "verificacoes": [], "correcao_recuperada": None,
        "barreira": "nao_avaliada", "contexto": [], "requisicoes": [],
        "custo_estimado_usd": None, "custo_faturado_usd": None, "situacao_custo": "nao_disponivel",
    }


def _resultado_inicial(numero, modo):
    historico, memoria = MODOS[modo]
    return {
        "pedido": numero, "cenario": modo, "modelo": MODELO,
        "configuracao": {"historico": historico, "limite_runs": 3 if historico else 0, "memoria_pessoal": memoria},
        "isolamento": "SQLite e chave HMAC temporários exclusivos da combinação",
        "turnos": [_novo_turno("diligencia_local"), _novo_turno("retomada_com_modelo")],
    }


def _classificar_falha(erro, evento):
    import httpx
    from openai import APIConnectionError, APIStatusError, APITimeoutError

    status = evento["http_status"] if evento is not None else None
    etapa = "preparacao" if evento is None else "transporte"
    if status is not None:
        etapa = "resposta_http" if status >= 300 else "resposta_modelo"
    tipo = "ErroNaoClassificado"
    codigo = None
    while erro is not None:
        if isinstance(erro, (APITimeoutError, httpx.TimeoutException)):
            tipo = "Timeout"
            break
        if isinstance(erro, (APIConnectionError, httpx.TransportError)):
            tipo = "ErroTransporte"
        if isinstance(erro, APIStatusError):
            tipo = "ErroHTTP"
            if isinstance(erro.code, str) and erro.code in {
                "invalid_api_key", "model_not_found", "insufficient_quota",
                "rate_limit_exceeded", "context_length_exceeded",
            }:
                codigo = erro.code
            break
        erro = erro.__cause__
    return {"tipo": tipo, "etapa": etapa, "http_status": status, "codigo_provedor": codigo}


def _cliente_openai(http, chave_api):
    from openai import OpenAI

    return OpenAI(api_key=chave_api, base_url="https://api.openai.com/v1", max_retries=0, http_client=http)


def _instruir(numero, modo, preparado, caminho, banco, medicao, chave_api, transporte):
    import httpx
    from agno.models.openai import OpenAIResponses
    from agente import criar_agente_reutilizavel

    class ModeloMedido(OpenAIResponses):
        def get_client(self):
            # O Agno remove o cliente na cópia usada pelo gerenciador de memória.
            return cliente

        def invoke(self, messages, **kwargs):
            with medicao.observar_falha():
                captura = medicao.capturar(messages, kwargs.get("run_response"))
                token = medicao.atual.set(captura)
                try:
                    return super().invoke(messages, **kwargs)
                finally:
                    medicao.atual.reset(token)

    historico, memoria = MODOS[modo]
    agente = criar_agente_reutilizavel(
        usar_memoria=historico, memoria_usuario=memoria, caminho_banco=caminho if historico else None,
        banco_protegido=banco if historico else None,
    )
    with httpx.Client(
        transport=transporte, follow_redirects=False, timeout=40,
        verify=ssl.create_default_context(),
        event_hooks={"request": [medicao.antes_requisicao], "response": [medicao.depois_resposta]},
    ) as http:
        cliente = _cliente_openai(http, chave_api)
        agente.model = ModeloMedido(
            id=MODELO, client=cliente, parallel_tool_calls=False, reasoning_effort="none",
            store=False, use_previous_response_id=False, retries=0,
        )
        try:
            return agente.run(
                pedido=preparado["pedido_corrigido"], session_id=numero, user_id=preparado["user_id"],
                run_id=str(uuid4()), retomar_complementacao=True, caminho_banco_administrativo=caminho,
            )
        finally:
            # Um erro de análise não deve deixar a tarefa de memória escrevendo após o relatório.
            if agente._background_executor is not None:
                agente._background_executor.shutdown(wait=True, cancel_futures=True)


def executar_combinacao(numero, modo, chave_api, *, transporte=None):
    if numero not in PEDIDOS or modo not in MODOS:
        raise ValueError("combinação fora do experimento autorizado")

    from agno.run.agent import RunStatus
    from auditoria_execucao import registrar_ferramentas
    from barreira_persistente import BarreiraPersistente
    from barreira_validacao import validar_instrucao
    from complementacoes import CAMPOS_COMPLEMENTAVEIS, aplicar_complementacao
    from execucao_interativa import _ler_instrucao, _publicar_instrucao, executar_tentativa
    from persistencia_sessoes import preparar_pedido_complementado, registrar_complementacao, registrar_diligencia

    registro = _resultado_inicial(numero, modo)
    local, retorno = registro["turnos"]
    medicao = None
    inicio = perf_counter()
    try:
        with TemporaryDirectory() as pasta:
            caminho = Path(pasta).resolve() / "experimento.db"
            caminho.touch(exist_ok=False)
            caminhos = {"caminho_banco": caminho, "banco_autorizado": caminho}
            barreira = BarreiraPersistente(secrets.token_bytes(32))
            barreira.preparar(**caminhos)
            complemento = aplicar_complementacao(numero)
            original, corrigido = complemento["pedido_original"], complemento["pedido_corrigido"]
            titular = corrigido["matricula"]
            barreira.vincular_protocolo_validado(numero, titular, **caminhos)
            preliminar = executar_tentativa(
                protocolo=numero, tentativa_id=str(uuid4()), pedido=original, session_id=numero, user_id=None,
            )
            if preliminar["status"] != "conferida":
                raise RuntimeError("diligencia_local_recusada")
            instrucao_local = preliminar["instrucao_conferida"]
            with barreira.abrir_agno(titular, **caminhos) as banco:
                inicial = registrar_diligencia(numero, caminho_banco=caminho, banco_protegido=banco)
                if inicial.session_id != numero or inicial.user_id is not None:
                    raise RuntimeError("sessao_preliminar_invalida")
                local.update(
                    status="conferido", session_id=numero,
                    situacao_original="retorno_ausente" if numero.endswith("0111") else "divergencia_cadastral",
                    recomendacao=instrucao_local["recomendacao"], verificacoes=_verificacoes(instrucao_local),
                    barreira="aprovada", segundos=round(perf_counter() - inicio, 6), situacao_custo="sem_chamada",
                )
                inicio = perf_counter()
                campo = CAMPOS_COMPLEMENTAVEIS[numero]
                registrar_complementacao(numero, {campo: corrigido[campo]}, caminho_banco=caminho, banco_protegido=banco)
                preparado = preparar_pedido_complementado(numero, caminho_banco=caminho)
                if preparado["pedido_corrigido"] != corrigido or (preparado["session_id"], preparado["user_id"]) != (
                    numero, titular,
                ):
                    raise RuntimeError("correcao_persistida_incompativel")
                retorno.update(
                    session_id=numero, user_id=titular,
                    correcao_recuperada={"campo": campo, "valor_validado": corrigido[campo]},
                )
                divergente = original["matricula"] if numero.endswith("0112") else None
                medicao = Medicao(preparado, divergente)
                resposta = _instruir(numero, modo, preparado, caminho, banco, medicao, chave_api, transporte)
                barreira.confirmar_admissao(banco, titular)
                retorno["runs_persistidos"] = len(banco.get_runs(session_id=numero, user_id=titular))
                retorno["memorias_persistidas"] = len(banco.get_user_memories(user_id=titular))
                if medicao.falhas or any(e["http_status"] is None or e["http_status"] >= 400 for e in medicao.requisicoes):
                    raise RuntimeError("falha_na_requisicao")
                if resposta.status is not RunStatus.completed:
                    raise RuntimeError("run_nao_concluido")
                if (resposta.session_id, resposta.user_id) != (numero, titular):
                    raise RuntimeError("resposta_fora_da_sessao")
                instrucao = _ler_instrucao(resposta.content)
                parecer = validar_instrucao(corrigido, instrucao, registrar_ferramentas(resposta))
                retorno["barreira"] = "recusada"
                try:
                    conferida = _publicar_instrucao(parecer, numero, titular, preliminar=False)
                except (ValueError, TypeError):
                    retorno["status"] = "analise_manual"
                else:
                    retorno.update(status="conferido", barreira="aprovada", recomendacao=conferida["recomendacao"],
                                   verificacoes=_verificacoes(conferida))
    except Exception as exc:
        turno = retorno if local["status"] == "conferido" else local
        turno.update(status="erro", classe_erro=type(exc).__name__)
    finally:
        turno = retorno if local["status"] == "conferido" else local
        turno["segundos"] = round(perf_counter() - inicio, 6)
        if medicao is not None:
            medicao.acumular(retorno)
    return registro


def _verificacoes(instrucao):
    return [{chave: item[chave] for chave in ("criterio", "situacao")} for item in instrucao["verificacoes"]]


def _gravar_json(caminho, dados):
    with caminho.open("x", encoding="utf-8") as arquivo:
        json.dump(dados, arquivo, ensure_ascii=False, indent=2)
        arquivo.write("\n")


def _suspensao(registro):
    for evento in registro["turnos"][1]["requisicoes"]:
        status = evento["http_status"]
        if status is None:
            return "falha_de_transporte_ou_conexao"
        if status in (401, 403, 404, 429):
            return f"http_{status}"
    return None


def gravar_resumo(destino, registros, inicio):
    _gravar_json(destino / "resumo_comparativo.json", {
        "inicio_utc": inicio, "tarifa_referencia": TARIFA, "combinacoes": registros,
    })
    linhas = [
        "# Experimento de memória nas complementações 0111 e 0112", "",
        "Projeto individual de Yasmine Lino Franco.", "",
        "Cada combinação usou SQLite e chave HMAC temporários próprios. Em A, somente a trilha "
        "administrativa usou SQLite. Em B e C, o Agno também persistiu runs com limite de três. "
        "C habilitou atualização de memória pessoal.", "",
        "O primeiro turno é uma diligência local. Portanto, não há tokens do modelo nesse turno "
        "nem conversa anterior do modelo para recuperar no segundo. O resumo administrativo é recuperado "
        "da mesma sessão em todos os cenários. A memória pessoal, quando gerada, é contabilizada sem exportar seu conteúdo.", "",
        "| Pedido | Cenário | Turno | Status | Chamadas HTTP observadas | Entrada | Saída | Total | Tempo (s) | USD estimado | Barreira |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for registro in registros:
        for i, turno in enumerate(registro["turnos"], start=1):
            campos = (
                registro["pedido"], registro["cenario"], i, turno["status"], turno["chamadas_ao_modelo"],
                *(turno[k] for k in _TOKENS), turno["segundos"], turno["custo_estimado_usd"], turno["barreira"],
            )
            linhas.append("| " + " | ".join("—" if x is None else str(x) for x in campos) + " |")
    linhas += [
        "", f"Tarifa padrão consultada em 22/11/2026. [GPT-5.6 Luna]({FONTE_TARIFA})", "",
        "A estimativa usa apenas o consumo reportado, sem descontos, impostos ou acréscimos não informados. "
        "O custo faturado permanece indisponível. Requisições recusadas ou sem métricas ficam sem tokens e custo. "
        "A contagem HTTP registra tentativas observadas no cliente; uma tentativa sem resposta não comprova processamento no provedor.",
        "", "Os JSONs individuais trazem estado de validação, sessão, titular sintético, correção e inventário "
        "do contexto capturado, sem mensagem integral, credencial ou memória pessoal bruta.",
    ]
    motivos = sorted({r["motivo_nao_executado"] for r in registros if r.get("motivo_nao_executado")})
    if motivos:
        linhas += ["", "Combinações não executadas ficaram registradas com o motivo: " + ", ".join(motivos) + "."]
    with (destino / "RELATORIO.md").open("x", encoding="utf-8") as arquivo:
        arquivo.write("\n".join(linhas) + "\n")


def main():
    if sys.argv[1:] != ["--executar-seis"]:
        raise SystemExit("Use --executar-seis após a validação offline.")
    if version("agno") != "3.2.1":
        raise SystemExit("Versão do Agno incompatível.")
    try:
        SAIDA.mkdir(exist_ok=False)
    except FileExistsError:
        raise SystemExit("A pasta da execução já existe. Repetição automática recusada.") from None

    inicio = datetime.now(timezone.utc).isoformat()
    resultados = []
    motivo = None
    with open(os.devnull, "w", encoding="utf-8") as silencio:
        with redirect_stdout(silencio), redirect_stderr(silencio):
            try:
                import agente  # Carrega a configuração existente sem imprimir seu conteúdo.
            except Exception:
                motivo = "configuracao_do_agente_indisponivel"
            chave = os.getenv("OPENAI_API_KEY")
            if not chave or not chave.strip() or chave.strip() == "coloque_sua_chave_aqui":
                motivo = motivo or "credencial_nao_configurada"

        for numero in PEDIDOS:
            for modo in MODOS:
                if motivo is not None:
                    registro = _resultado_inicial(numero, modo)
                    registro["motivo_nao_executado"] = motivo
                else:
                    print(f"Iniciando {numero} / {modo}.", flush=True)
                    with redirect_stdout(silencio), redirect_stderr(silencio):
                        registro = executar_combinacao(numero, modo, chave)
                    motivo = _suspensao(registro)
                resultados.append(registro)
                _gravar_json(SAIDA / f"{numero}_{modo}.json", registro)
                print(f"{numero} / {modo}: {registro['turnos'][1]['status']}.", flush=True)
    gravar_resumo(SAIDA, resultados, inicio)
    return 0 if all(r["turnos"][1]["status"] == "conferido" for r in resultados) else 1


if __name__ == "__main__":
    raise SystemExit(main())
