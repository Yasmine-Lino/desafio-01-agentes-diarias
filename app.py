from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from importlib.util import find_spec
from pathlib import Path
from time import time
from uuid import uuid4

import streamlit as st
from pydantic import ValidationError

from barreira_persistente import BarreiraPersistente, _TRABALHO, caminho_validado, exige_admissao
from complementacoes import CAMPOS_COMPLEMENTAVEIS, obter_pedido
from execucao_interativa import consultas_publicaveis, executar_tentativa
from exclusao_memoria import excluir_memoria_titular
from modelos import Instrucao
from persistencia_sessoes import (
    preparar_pedido_complementado,
    registrar_complementacao,
    registrar_diligencia,
)
from seguranca import sanitizar_texto
from validacao_pedido import validar_pedido

BASE = Path(__file__).resolve().parent
PASTA_RESULTADOS = BASE / "resultados" / "execucoes"
PASTA_REVISOES = BASE / "resultados" / "revisoes_humanas"
BANCO_COMPLEMENTACOES = _TRABALHO

CRITERIOS = {
    "cadastro": "Cadastro do servidor",
    "dados_completos": "Dados completos",
    "antecedencia": "Antecedência do pedido",
    "prestacao_contas": "Prestação de contas",
    "limite_mensal": "Limite mensal de diárias",
    "saldo_orcamentario": "Saldo orçamentário",
}

SITUACOES = {
    "atende": "Atende",
    "nao_atende": "Não atende",
    "nao_verificado": "Não verificado",
}

RECOMENDACOES = {
    "apto_para_autorizacao": "Apto para autorização",
    "diligencia": "Diligência",
    "nao_recomendado": "Não recomendado",
}


PROTOCOLO = re.compile(r"DIA-[0-9]{4}-[0-9]{4}")
MATRICULA = re.compile(r"[0-9]{6}")
EXECUCAO = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
CRITERIOS_MERITO = ("antecedencia", "prestacao_contas", "limite_mensal", "saldo_orcamentario")
CONSULTAS = {
    ("verificar_cadastro", "consultar_servidor"),
    ("verificar_prestacoes", "consultar_historico"),
    ("verificar_calculo", "calcular_diarias"),
    ("verificar_orcamento", "calcular_diarias"),
    ("verificar_orcamento", "consultar_saldo"),
}
MENSAGEM_MANUAL = (
    "Instrução indisponível para revisão automatizada. "
    "Encaminhe o pedido para análise manual."
)


def _dicionario(dados, chave, alternativa):
    valor = dados[chave] if chave in dados else dados.get(alternativa)
    return valor if isinstance(valor, dict) else {}


def _auditoria_sem_merito(auditoria):
    return (
        auditoria.get("chamadas") == []
        and auditoria.get("chamadas_python", []) == []
        and auditoria.get("estado_trilha") in (None, "ausente", "vazia")
        and auditoria.get("estado_contexto") in (None, "ausente")
        and auditoria.get("contexto_execucao") is None
        and auditoria.get("nomes_ferramentas", []) == []
        and type(auditoria.get("total_chamadas", 0)) is int
        and auditoria.get("total_chamadas", 0) == 0
    )


def _execucao_confere(dados, barreira, auditoria, instrucao):
    contexto = auditoria.get("contexto_execucao")
    if (
        auditoria.get("estado_contexto") != "completo"
        or auditoria.get("estado_trilha") != "completa"
        or not isinstance(contexto, dict)
        or contexto.get("protocolo") != instrucao.numero_pedido
        or contexto.get("session_id") != instrucao.numero_pedido
        or contexto.get("matricula") != instrucao.matricula
        or contexto.get("user_id") != instrucao.matricula
    ):
        return False
    run_id = contexto.get("run_id")
    if not isinstance(run_id, str) or EXECUCAO.fullmatch(run_id) is None:
        return False
    for origem in (dados, barreira):
        for chave, esperado in (
            ("run_id", run_id),
            ("session_id", instrucao.numero_pedido),
            ("user_id", instrucao.matricula),
        ):
            if chave in origem and origem[chave] != esperado:
                return False

    agno = auditoria.get("chamadas")
    python = auditoria.get("chamadas_python")
    ferramentas = {nome for nome, _ in CONSULTAS}
    if (
        not isinstance(agno, list) or len(agno) != len(ferramentas)
        or not isinstance(python, list) or len(python) != len(CONSULTAS)
        or type(auditoria.get("total_chamadas")) is not int
        or auditoria["total_chamadas"] != len(ferramentas)
        or not all(isinstance(chamada, dict) and chamada.get("erro") is False
                   for chamada in agno + python)
    ):
        return False

    nomes = [chamada.get("nome") for chamada in agno]
    ids = [chamada.get("tool_call_id") for chamada in agno]
    if (
        not all(isinstance(nome, str) and nome in ferramentas for nome in nomes)
        or set(nomes) != ferramentas
        or auditoria.get("nomes_ferramentas") != nomes
        or not all(isinstance(chave, str) and chave for chave in ids)
        or len(set(ids)) != len(ids)
    ):
        return False

    consultas = {}
    for chamada in python:
        par = (chamada.get("ferramenta_agno"), chamada.get("nome"))
        argumentos = chamada.get("argumentos")
        resultado = chamada.get("resultado")
        if (
            not all(isinstance(item, str) for item in par)
            or par not in CONSULTAS or par in consultas
            or chamada.get("executada") is not True
            or not isinstance(argumentos, dict)
            or argumentos.get("matricula") != instrucao.matricula
            or not isinstance(resultado, dict)
            or resultado.get("matricula") != instrucao.matricula
        ):
            return False
        consultas[par] = chamada

    for chamada in agno:
        nome = chamada["nome"]
        consulta = next(
            registro for (ferramenta, funcao), registro in consultas.items()
            if ferramenta == nome
            and (nome != "verificar_orcamento" or funcao == "consultar_saldo")
        )
        if (
            chamada.get("argumentos") != consulta["argumentos"]
            or chamada.get("resultado") != consulta["resultado"]
        ):
            return False

    for ferramenta in ("verificar_calculo", "verificar_orcamento"):
        efetivos = consultas[(ferramenta, "calcular_diarias")]["argumentos"]
        for campo in ("destino_uf", "data_pedido", "data_partida", "data_retorno", "data_analise"):
            if not isinstance(contexto.get(campo), str) or efetivos.get(campo) != contexto[campo]:
                return False
    historico = consultas[("verificar_prestacoes", "consultar_historico")]["argumentos"]
    mes_referencia = contexto["data_partida"][:7]
    calculo = consultas[("verificar_calculo", "calcular_diarias")]
    interno = consultas[("verificar_orcamento", "calcular_diarias")]
    saldo = consultas[("verificar_orcamento", "consultar_saldo")]
    if (
        historico.get("data_analise") != contexto["data_analise"]
        or historico.get("mes_referencia") != mes_referencia
        or calculo["argumentos"].get("mes_referencia") != mes_referencia
        or interno["argumentos"] != calculo["argumentos"]
        or interno["resultado"] != calculo["resultado"]
        or type(calculo["resultado"].get("valor_total")) not in (int, float)
        or saldo["argumentos"].get("valor_solicitado") != calculo["resultado"]["valor_total"]
        or saldo["resultado"].get("valor_solicitado") != calculo["resultado"]["valor_total"]
    ):
        return False
    calculo = calculo["resultado"]
    if instrucao.recomendacao == "diligencia":
        return True
    return (
        type(calculo.get("quantidade_diarias")) in (int, float)
        and type(calculo.get("valor_total")) in (int, float)
        and calculo["quantidade_diarias"] == instrucao.quantidade_diarias
        and calculo["valor_total"] == instrucao.valor_total
    )


def _ler_instrucao_conferida(valor, protocolo):
    if not isinstance(valor, dict):
        return None
    try:
        instrucao = Instrucao.model_validate(valor, strict=True)
    except ValidationError:
        return None
    if (
        PROTOCOLO.fullmatch(instrucao.numero_pedido) is None
        or MATRICULA.fullmatch(instrucao.matricula) is None
        or instrucao.numero_pedido != protocolo
    ):
        return None
    textos = [
        instrucao.minuta_despacho, *instrucao.pendencias, *instrucao.alertas,
        *(verificacao.detalhe for verificacao in instrucao.verificacoes),
    ]
    if any(not texto.strip() or sanitizar_texto(texto) != texto for texto in textos):
        return None
    return instrucao


def _rotular_instrucao(instrucao, *, preliminar):
    situacoes = {item.criterio: item.situacao for item in instrucao.verificacoes}
    diligencia = instrucao.recomendacao == "diligencia"
    if diligencia:
        if instrucao.quantidade_diarias is not None or instrucao.valor_total is not None or not instrucao.pendencias:
            return None
    elif instrucao.quantidade_diarias is None or instrucao.valor_total is None:
        return None

    if preliminar:
        if (
            not diligencia or instrucao.exige_autorizacao_superior
            or any(situacoes[criterio] != "nao_verificado" for criterio in CRITERIOS_MERITO)
        ):
            return None
        return "Diligência preliminar"

    if (
        "nao_verificado" in situacoes.values()
        or (diligencia and (
            not instrucao.exige_autorizacao_superior or situacoes["antecedencia"] != "nao_atende"
        ))
        or (not diligencia and instrucao.exige_autorizacao_superior)
        or (instrucao.recomendacao == "apto_para_autorizacao" and "nao_atende" in situacoes.values())
        or (instrucao.recomendacao == "nao_recomendado" and "nao_atende" not in situacoes.values())
    ):
        return None
    return "Diligência após análise de mérito" if diligencia else "Análise de mérito"


def instruir_revisao(dados):
    """Valida um artefato gravado, exclusivo da consulta histórica."""
    barreira = _dicionario(dados, "barreira_validacao", "validacao")
    auditoria = _dicionario(dados, "auditoria_ferramentas", "auditoria")
    protocolo = dados.get("numero_pedido")
    if (
        barreira.get("aprovado") is not True
        or barreira.get("texto_conferido") is not True
        or barreira.get("erros") != []
        or barreira.get("numero_pedido") != protocolo
    ):
        return None
    instrucao = _ler_instrucao_conferida(barreira.get("instrucao_conferida"), protocolo)
    if instrucao is None:
        return None
    preliminar = dados.get("tipo_execucao") == "diligencia_preliminar"
    rotulo = _rotular_instrucao(instrucao, preliminar=preliminar)
    if rotulo is None:
        return None
    if preliminar:
        return (instrucao, rotulo, None, []) if _auditoria_sem_merito(auditoria) else None
    if not _execucao_confere(dados, barreira, auditoria, instrucao):
        return None
    return instrucao, rotulo, auditoria["contexto_execucao"]["run_id"], consultas_publicaveis(
        auditoria, instrucao.matricula,
    )


def carregar_protocolos():
    with (BASE / "dados" / "pedidos.json").open(encoding="utf-8-sig") as arquivo:
        acervo = json.load(arquivo)
    return sorted({
        item["numero"] for item in acervo
        if isinstance(item, dict) and isinstance(item.get("numero"), str)
        and PROTOCOLO.fullmatch(item["numero"])
    })


def _resultado_interativo(resultado, protocolo, tentativa_id, matricula, *, preliminar):
    """Valida o retorno direto do serviço, que já passou pela barreira."""
    tipo_esperado = "diligencia_preliminar" if preliminar else "analise_merito"
    run_id = None if preliminar else tentativa_id
    if (
        not isinstance(resultado, dict)
        or resultado.get("status") != "conferida"
        or resultado.get("protocolo") != protocolo
        or resultado.get("tentativa_id") != tentativa_id
        or resultado.get("tipo_execucao") != tipo_esperado
        or resultado.get("revisao_humana_obrigatoria") is not True
        or resultado.get("run_id") != run_id
        or any(campo in resultado and resultado[campo] is not True
               for campo in ("aprovado", "texto_conferido"))
    ):
        return None
    instrucao = _ler_instrucao_conferida(resultado.get("instrucao_conferida"), protocolo)
    if instrucao is None or instrucao.matricula != matricula:
        return None
    rotulo = _rotular_instrucao(instrucao, preliminar=preliminar)
    consultas = resultado.get("consultas", [])
    if not isinstance(consultas, list) or (preliminar and consultas):
        return None
    return (instrucao, rotulo, run_id, consultas_publicaveis(
        {"chamadas_python": consultas}, instrucao.matricula,
    )) if rotulo is not None else None


@dataclass(frozen=True)
class AcessoTitular:
    emissor: str
    sujeito: str
    matricula: str
    protocolos: frozenset[str]


def _titulares_configurados():
    entradas = json.loads(os.getenv("TITULARES_OIDC_JSON") or "null")
    if not isinstance(entradas, list) or not entradas:
        raise ValueError("Cadastro OIDC indisponível.")
    acessos = {}
    vinculos = {}
    for entrada in entradas:
        if not isinstance(entrada, dict):
            raise ValueError("Cadastro OIDC inválido.")
        emissor, sujeito, matricula, protocolos = (
            entrada.get(campo) for campo in ("iss", "sub", "matricula", "protocolos")
        )
        if (
            not all(isinstance(valor, str) and valor.strip() for valor in (emissor, sujeito, matricula))
            or not MATRICULA.fullmatch(matricula)
            or not isinstance(protocolos, list)
            or any(not isinstance(p, str) or not PROTOCOLO.fullmatch(p) for p in protocolos)
            or (emissor, sujeito) in acessos
        ):
            raise ValueError("Cadastro OIDC inválido.")
        for protocolo in protocolos:
            if vinculos.setdefault(protocolo, matricula) != matricula:
                raise ValueError("Vínculo de protocolo ambíguo.")
        acessos[emissor, sujeito] = AcessoTitular(emissor, sujeito, matricula, frozenset(protocolos))
    return acessos


def _acesso_protegido():
    chave = os.getenv("BARREIRA_HMAC_CHAVE_HEX", "")
    try:
        if re.fullmatch(r"[0-9a-fA-F]{64}", chave) is None:
            raise ValueError("Chave HMAC indisponível.")
        titulares = _titulares_configurados()
    except (ValueError, RecursionError):
        _limpar_identidade_interativa(None)
        st.warning("Operações protegidas indisponíveis. A administração deve configurar a autenticação OIDC, "
                   "os vínculos de titulares e uma chave HMAC estável.")
        st.stop()

    try:
        usuario = st.user
        logado = usuario.get("is_logged_in") is True
    except Exception:
        logado = False
    if logado:
        emissor, sujeito, expira = (usuario.get(campo) for campo in ("iss", "sub", "exp"))
        if type(expira) is int and expira > time():
            if isinstance(emissor, str) and isinstance(sujeito, str):
                acesso = titulares.get((emissor, sujeito))
                if acesso is not None:
                    _limpar_identidade_interativa(acesso)
                    return acesso, BarreiraPersistente(bytes.fromhex(chave))
            _limpar_identidade_interativa(None)
            st.warning("A identidade autenticada não possui um vínculo de titular autorizado.")
            st.stop()

    _limpar_identidade_interativa(None)
    st.info("Autenticação do titular obrigatória para acessar as operações protegidas.")
    if find_spec("authlib") is None:
        st.warning("Autenticação OIDC indisponível neste ambiente. Solicite a configuração à administração.")
        st.stop()
    if st.button("Entrar com provedor de identidade"):
        try:
            st.login()
        except Exception:
            st.warning("Autenticação indisponível. Solicite à administração a configuração do provedor OIDC.")
    st.stop()


def _limpar_identidade_interativa(acesso):
    identidade = None if acesso is None else (
        acesso.emissor, acesso.sujeito, acesso.matricula, tuple(sorted(acesso.protocolos)),
    )
    if st.session_state.get("acesso_titular") != identidade:
        _limpar_fluxo_interativo()
        st.session_state.pop("protocolo_interativo", None)
        st.session_state.pop("pedido_interativo", None)
        st.session_state["chave_exclusao"] = str(uuid4())
        st.session_state["acesso_titular"] = identidade


def _banco_complementacoes():
    banco = BANCO_COMPLEMENTACOES
    if banco.resolve() != banco or banco.is_symlink():
        raise ValueError("Banco de trabalho incompatível.")
    if not banco.exists():
        try:
            with banco.open("xb"):
                pass
        except FileExistsError:
            pass
    if caminho_validado(banco, banco) is None:
        raise ValueError("Banco de trabalho incompatível.")
    return banco


def _executar_exclusao(acesso, barreira):
    with st.form(f"exclusao_{st.session_state['chave_exclusao']}", clear_on_submit=True):
        confirmado = st.checkbox("Confirmo a exclusão dos dados do meu titular e o bloqueio de novas gravações.")
        solicitar = st.form_submit_button("Solicitar exclusão")
    if not solicitar:
        return
    if not confirmado:
        st.warning("Confirme explicitamente a exclusão para prosseguir.")
        return
    try:
        banco = _banco_complementacoes()
        resultado = excluir_memoria_titular(
            acesso.matricula, caminho_banco=banco, banco_autorizado=banco, barreira=barreira,
        )
    except Exception:
        st.error("Não foi possível processar a solicitação. Encaminhe para revisão manual.")
        return
    _limpar_fluxo_interativo()
    mensagens = {
        "excluido": "Exclusão lógica executada.",
        "sem_registros": "Nenhum registro próprio encontrado para excluir.",
        "bloqueado": "Solicitação bloqueada para conferência.",
        "erro": "Exclusão interrompida.",
    }
    st.write(mensagens.get(resultado.get("status"), "Estado indisponível."))
    if resultado.get("bloqueio_confirmado") is True:
        st.info("O bloqueio de novas gravações foi confirmado.")
    for etapa, rotulo in (("antes", "Antes"), ("depois", "Depois")):
        contagens = resultado.get(etapa)
        if isinstance(contagens, dict):
            for campo, categoria in (("sessoes", "Sessões"), ("execucoes", "Execuções"), ("memorias", "Memórias")):
                quantidade = contagens.get(campo)
                if type(quantidade) is int and quantidade >= 0:
                    st.write(f"{rotulo} · {categoria} · {quantidade}")
    residuos = resultado.get("residuos")
    if isinstance(residuos, dict):
        for tabela, categoria in (
            ("agno_sessions", "Sessões"), ("agno_runs", "Execuções"), ("agno_memories", "Memórias"),
        ):
            quantidade = residuos.get(tabela)
            if type(quantidade) is int and quantidade > 0:
                st.write(f"Resíduos · {categoria} · {quantidade}")
    if resultado.get("revisao_manual") is True:
        st.warning("Revisão manual necessária. Registros com vínculo incerto ou de terceiros são preservados.")
        if resultado.get("nome_verificado") is False:
            st.info("A conferência por nome cadastral não foi concluída.")


def _estado_administrativo(sessao, protocolo, titular):
    if sessao.session_id != protocolo or not isinstance(sessao.metadata, dict):
        raise ValueError("Sessão administrativa inválida.")
    estado = sessao.metadata.get("estado")
    if estado == "aguardando_complementacao" and sessao.user_id is None:
        return estado
    if estado == "complementado" and sessao.user_id == titular:
        return estado
    raise ValueError("Estado administrativo incompatível.")


def _executar_pedido_selecionado(protocolo, tentativa_id, acesso, barreira, banco, *, retomar=False):
    with st.status("Validando o pedido", expanded=True) as progresso:
        try:
            if protocolo not in acesso.protocolos:
                return None, None
            if retomar:
                progresso.update(label="Recuperando a sessão original", state="running")
                preparado = preparar_pedido_complementado(protocolo, caminho_banco=banco)
                pedido = preparado["pedido_corrigido"]
                if preparado["session_id"] != protocolo:
                    return None, None
            else:
                pedido = obter_pedido(protocolo)

            matricula = pedido.get("matricula")
            if (
                pedido.get("numero") != protocolo
                or not isinstance(matricula, str)
                or MATRICULA.fullmatch(matricula.strip()) is None
            ):
                return None, None
            matricula = matricula.strip()
            merito = validar_pedido(pedido).get("pode_analisar_merito")
            if type(merito) is not bool:
                return None, None
            if matricula != acesso.matricula and (merito or protocolo != "DIA-2026-0112"):
                return None, None
            if retomar and (not merito or preparado["user_id"] != acesso.matricula):
                return None, None
            barreira.vincular_protocolo_validado(
                protocolo, acesso.matricula, caminho_banco=banco, banco_autorizado=banco,
            )

            progresso.update(label="Executando a análise", state="running")
            resultado = executar_tentativa(
                protocolo=protocolo,
                tentativa_id=tentativa_id,
                pedido=pedido,
                session_id=protocolo,
                user_id=matricula if merito else None,
                usar_memoria=merito,
                **({"caminho_banco": banco, "banco_autorizado": banco, "barreira_persistente": barreira}
                   if merito else {}),
            )
            progresso.update(label="Conferindo o resultado", state="running")
            revisavel = _resultado_interativo(
                resultado, protocolo, tentativa_id, matricula, preliminar=not merito,
            )
            if revisavel is None:
                return None, None
            if not merito and protocolo in CAMPOS_COMPLEMENTAVEIS:
                with barreira.abrir_agno(acesso.matricula, caminho_banco=banco, banco_autorizado=banco) as protegido:
                    sessao = registrar_diligencia(protocolo, caminho_banco=banco, banco_protegido=protegido)
                estado = _estado_administrativo(sessao, protocolo, acesso.matricula)
                # Uma sessão já complementada deve ser retomada pelos dados corrigidos.
                return (None if estado == "complementado" else revisavel), estado
            return revisavel, "complementado" if retomar else None
        except Exception:
            return None, None


def _limpar_tentativa_interativa():
    st.session_state.pop("tentativa_interativa", None)
    st.session_state.pop("falha_complementacao", None)
    st.session_state["chave_execucao"] = str(uuid4())


def _limpar_fluxo_interativo():
    _limpar_tentativa_interativa()
    st.session_state.pop("estado_complementacao", None)


def _formulario_complementacao(protocolo, campo, acesso, barreira, banco):
    if st.session_state.get("estado_complementacao") is None:
        return
    rotulo = "Data de retorno corrigida" if campo == "data_retorno" else "Matrícula corrigida"
    formato = "AAAA-MM-DD" if campo == "data_retorno" else "Seis dígitos"
    with st.form(f"complementar_{st.session_state['chave_execucao']}", clear_on_submit=True):
        valor = st.text_input(rotulo, placeholder=formato)
        enviar = st.form_submit_button("Registrar complementação")
    if not enviar:
        return

    _limpar_tentativa_interativa()
    try:
        if protocolo not in acesso.protocolos or (campo == "matricula" and valor != acesso.matricula):
            raise PermissionError("Complementação fora do vínculo autorizado.")
        with barreira.abrir_agno(acesso.matricula, caminho_banco=banco, banco_autorizado=banco) as protegido:
            sessao = registrar_complementacao(
                protocolo, {campo: valor}, caminho_banco=banco, banco_protegido=protegido,
            )
        if _estado_administrativo(sessao, protocolo, acesso.matricula) != "complementado":
            raise ValueError("Complementação não registrada.")
        st.session_state["estado_complementacao"] = "complementado"
    except Exception:
        st.session_state["falha_complementacao"] = True
    st.rerun()


def _selecionar_execucao_interativa(acesso, barreira, banco):
    try:
        protocolos = [protocolo for protocolo in carregar_protocolos() if protocolo in acesso.protocolos]
    except (OSError, ValueError, TypeError):
        protocolos = []
    if not protocolos:
        st.error(MENSAGEM_MANUAL)
        st.stop()

    protocolo = st.selectbox("Selecione o pedido", protocolos, key="pedido_interativo")
    if st.session_state.get("protocolo_interativo") != protocolo:
        _limpar_fluxo_interativo()
        st.session_state["protocolo_interativo"] = protocolo

    ocupada = st.session_state.get("execucao_em_andamento") is not None
    campo = CAMPOS_COMPLEMENTAVEIS.get(protocolo)
    complementado = st.session_state.get("estado_complementacao") == "complementado"
    chave = st.session_state["chave_execucao"]
    executar = st.button(
        "Executar análise", type="primary", key=f"executar_{chave}",
        disabled=ocupada or complementado,
    )
    retomar = False
    if campo is not None:
        retomar = st.button(
            "Retomar análise complementada", key=f"retomar_{chave}", disabled=ocupada,
        )
        if not ocupada:
            _formulario_complementacao(protocolo, campo, acesso, barreira, banco)

    if (executar or retomar) and not ocupada:
        tentativa_id = str(uuid4())
        _limpar_tentativa_interativa()
        tentativa = {"protocolo": protocolo, "id": tentativa_id, "revisavel": None}
        st.session_state["tentativa_interativa"] = tentativa
        st.session_state["execucao_em_andamento"] = tentativa_id
        try:
            revisavel, estado = _executar_pedido_selecionado(
                protocolo, tentativa_id, acesso, barreira, banco, retomar=retomar,
            )
            atual = st.session_state.get("tentativa_interativa")
            if atual and atual["id"] == tentativa_id:
                if estado is not None:
                    st.session_state["estado_complementacao"] = estado
                if estado == "complementado" and revisavel is None:
                    st.session_state.pop("tentativa_interativa")
                else:
                    st.session_state["tentativa_interativa"] = {**tentativa, "revisavel": revisavel}
        finally:
            if st.session_state.get("execucao_em_andamento") == tentativa_id:
                st.session_state.pop("execucao_em_andamento", None)
        st.rerun()

    if st.session_state.get("falha_complementacao"):
        st.error(MENSAGEM_MANUAL)
        st.stop()
    tentativa = st.session_state.get("tentativa_interativa")
    if tentativa is None or tentativa["protocolo"] != protocolo or ocupada:
        if complementado and not ocupada:
            st.success("Complementação registrada. Retome a análise para uma nova tentativa.")
        st.stop()
    return tentativa["id"], tentativa["revisavel"]


def carregar_resultados():
    resultados = []
    for caminho in sorted(PASTA_RESULTADOS.glob("*.json")):
        if caminho.is_symlink():
            continue
        try:
            with caminho.open(encoding="utf-8-sig") as arquivo:
                dados = json.load(arquivo)
        except (OSError, ValueError):
            continue
        if isinstance(dados, dict):
            resultados.append((caminho, dados))
    return resultados


def salvar_revisao(chave, revisao):
    PASTA_REVISOES.mkdir(parents=True, exist_ok=True)
    destino = PASTA_REVISOES / f"{chave}.json"
    with destino.open("x", encoding="utf-8") as arquivo:
        json.dump(revisao, arquivo, ensure_ascii=False, indent=2)


def exibir_lista(titulo, itens):
    st.markdown(f"**{titulo}**")
    if not itens:
        st.write("Nenhum registro.")
    for item in itens:
        st.text(f"• {item}")


def _rotulo_registro(indice):
    numero = resultados[indice][1].get("numero_pedido")
    if isinstance(numero, str) and PROTOCOLO.fullmatch(numero):
        return f"{numero} · Registro {indice + 1}"
    return f"Registro {indice + 1}"


st.set_page_config(
    page_title="Agente de Diárias — Revisão Humana",
    page_icon="📋",
    layout="wide",
)

st.title("Agente de Diárias")
st.caption("Instrução automatizada com revisão humana obrigatória")

modo = st.radio(
    "Modo de trabalho",
    ("Executar pedido", "Consultar resultados históricos", "Excluir memória e histórico do agente"),
    horizontal=True,
)
if st.session_state.get("modo_exibido") != modo:
    _limpar_fluxo_interativo()
    st.session_state["modo_exibido"] = modo

if modo == "Excluir memória e histórico do agente":
    st.subheader("Exclusão dos dados na memória do agente")
    st.caption("Abrange sessões, execuções, eventos administrativos e memórias da cópia de trabalho do agente. "
               "Registros oficiais, resultados históricos e revisões humanas ficam fora da solicitação.")

acesso, barreira_persistente = _acesso_protegido()
if modo == "Excluir memória e histórico do agente":
    _executar_exclusao(acesso, barreira_persistente)
    st.stop()

if modo == "Executar pedido":
    try:
        banco_trabalho = _banco_complementacoes()
        caminhos = {"caminho_banco": banco_trabalho, "banco_autorizado": banco_trabalho}
        if not exige_admissao(banco_trabalho):
            barreira_persistente.preparar(**caminhos)
        with barreira_persistente.abrir_agno(acesso.matricula, **caminhos):
            pass
    except PermissionError:
        _limpar_fluxo_interativo()
        st.warning("Novas gravações estão bloqueadas para este titular.")
        st.stop()
    except Exception:
        _limpar_fluxo_interativo()
        st.error("Banco de trabalho indisponível para operações protegidas.")
        st.stop()
    tentativa_id, revisavel = _selecionar_execucao_interativa(acesso, barreira_persistente, banco_trabalho)
    chave = f"interativa_{tentativa_id}"
    arquivo_resultado = None
else:
    tentativa_id = None
    resultados = []
    for arquivo, dados in carregar_resultados():
        protocolo_historico = dados.get("numero_pedido")
        if not isinstance(protocolo_historico, str) or protocolo_historico not in acesso.protocolos:
            continue
        revisao = instruir_revisao(dados)
        if revisao is not None and revisao[0].matricula == acesso.matricula:
            resultados.append((arquivo, dados, revisao))
    if not resultados:
        st.warning("Nenhum resultado histórico foi encontrado.")
        st.stop()
    selecionado = st.selectbox(
        "Selecione a execução histórica",
        options=range(len(resultados)),
        format_func=_rotulo_registro,
    )
    arquivo_resultado, _, revisavel = resultados[selecionado]
    chave = arquivo_resultado.stem

if revisavel is None:
    st.error(MENSAGEM_MANUAL)
    st.stop()

instrucao, tipo_analise, run_id, consultas = revisavel
st.caption(tipo_analise)
col1, col2, col3, col4 = st.columns(4)
col1.metric("Pedido", instrucao.numero_pedido)
quantidade = instrucao.quantidade_diarias
col2.metric("Diárias", f"{quantidade:g}".replace(".", ",") if quantidade is not None else "—")
valor = instrucao.valor_total
valor_formatado = (
    f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if valor is not None else "—"
)
col3.metric("Valor total", valor_formatado)
col4.metric("Recomendação", RECOMENDACOES[instrucao.recomendacao])
st.write("**Autorização superior exigida:**", "Sim" if instrucao.exige_autorizacao_superior else "Não")

st.subheader("Verificações normativas")
for verificacao in instrucao.verificacoes:
    with st.expander(f"{CRITERIOS[verificacao.criterio]} — {SITUACOES[verificacao.situacao]}"):
        st.text(verificacao.detalhe)

col_pendencias, col_alertas = st.columns(2)
with col_pendencias:
    exibir_lista("Pendências", instrucao.pendencias)
with col_alertas:
    exibir_lista("Alertas", instrucao.alertas)

if consultas:
    st.subheader("Consultas executadas")
    for consulta in consultas:
        with st.expander(f"{consulta['ferramenta_agno']} · {consulta['nome']}"):
            for campo, valor in consulta["argumentos"].items():
                st.text(f"{campo} · {valor}")

st.divider()
st.subheader("Revisão humana obrigatória")
st.caption("A decisão final cabe ao ordenador de despesa.")

if (PASTA_REVISOES / f"{chave}.json").exists():
    st.success("Este resultado já possui uma revisão humana registrada.")
    st.stop()

identidade_formulario = json.dumps(
    [chave, run_id, instrucao.model_dump(mode="json")], sort_keys=True
)
chave_formulario = sha256(identidade_formulario.encode("utf-8")).hexdigest()

with st.form(f"revisao_{chave_formulario}"):
    revisor = st.text_input("Identificação do revisor")

    decisao = st.selectbox(
        "Decisão humana",
        options=[
            "solicitar_diligencia",
            "nao_autorizar",
            "encaminhar_para_autorizacao",
        ],
        format_func=lambda valor: {
            "solicitar_diligencia": "Solicitar diligência",
            "nao_autorizar": "Não autorizar",
            "encaminhar_para_autorizacao": "Encaminhar para autorização",
        }[valor],
    )

    despacho = st.text_area(
        "Minuta de despacho — editável",
        value=instrucao.minuta_despacho,
        height=220,
    )

    justificativa = st.text_area(
        "Justificativa da decisão ou divergência",
        height=120,
    )

    confirmar = st.checkbox(
        "Confirmo que analisei as verificações, pendências, "
        "alertas e evidências disponíveis."
    )

    enviar = st.form_submit_button(
        "Registrar decisão humana",
        type="primary",
    )

if enviar:
    divergencia = (
        decisao == "encaminhar_para_autorizacao"
        and instrucao.recomendacao != "apto_para_autorizacao"
    ) or (
        decisao == "solicitar_diligencia"
        and instrucao.recomendacao != "diligencia"
    ) or (
        decisao == "nao_autorizar"
        and instrucao.recomendacao != "nao_recomendado"
    )

    if not revisor.strip():
        st.error("Informe a identificação do revisor.")
    elif not despacho.strip():
        st.error("O despacho não pode ficar vazio.")
    elif not confirmar:
        st.error("Confirme a revisão das evidências.")
    elif divergencia and not justificativa.strip():
        st.error("Justifique a divergência em relação à recomendação.")
    elif (
        decisao == "encaminhar_para_autorizacao"
        and (
            instrucao.recomendacao != "apto_para_autorizacao"
            or instrucao.exige_autorizacao_superior
        )
    ):
        st.error(
            "O encaminhamento está bloqueado: a barreira deve estar "
            "aprovada, a recomendação deve ser apta e não pode haver "
            "autorização superior pendente."
        )
    else:
        revisao = {
            "numero_pedido": instrucao.numero_pedido,
            "arquivo_resultado": arquivo_resultado.name if arquivo_resultado is not None else None,
            "tentativa_id": tentativa_id,
            "data_registro": datetime.now().astimezone().isoformat(),
            "revisor": revisor.strip(),
            "decisao_humana": decisao,
            "recomendacao_agente": instrucao.recomendacao,
            "divergencia": divergencia,
            "justificativa": justificativa.strip(),
            "despacho_final": despacho.strip(),
            "barreira_aprovada": True,
            "texto_conferido": True,
            "run_id": run_id,
            "revisao_confirmada": True,
            "decisao_final_ordenador": False,
        }

        try:
            salvar_revisao(chave, revisao)
        except FileExistsError:
            st.error(
                "Já existe uma revisão registrada. "
                "Nenhum arquivo foi sobrescrito."
            )
        except OSError:
            st.error("Não foi possível registrar a revisão humana.")
        else:
            st.success(
                "Revisão humana registrada. "
                "O encaminhamento não substitui a decisão do "
                "ordenador de despesa."
            )
