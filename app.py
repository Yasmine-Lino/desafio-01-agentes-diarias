from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import streamlit as st

BASE = Path(__file__).resolve().parent
PASTA_RESULTADOS = BASE / "resultados" / "execucoes"
PASTA_REVISOES = BASE / "resultados" / "revisoes_humanas"

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


def carregar_resultados():
    resultados = {}

    for caminho in sorted(PASTA_RESULTADOS.glob("*.json")):
        try:
            with caminho.open(encoding="utf-8") as arquivo:
                dados = json.load(arquivo)

            numero = dados.get("numero_pedido")
            instrucao = dados.get("instrucao")

            if numero and isinstance(instrucao, dict):
                resultados[caminho.stem] = {
                    "arquivo": caminho,
                    "dados": dados,
                }
        except (OSError, ValueError):
            continue

    return resultados


def carregar_revisao(chave):
    caminho = PASTA_REVISOES / f"{chave}.json"

    if not caminho.exists():
        return None

    with caminho.open(encoding="utf-8") as arquivo:
        return json.load(arquivo)


def salvar_revisao(chave, revisao):
    PASTA_REVISOES.mkdir(parents=True, exist_ok=True)
    destino = PASTA_REVISOES / f"{chave}.json"

    # Preserva a primeira decisão: não sobrescreve revisões anteriores.
    with destino.open("x", encoding="utf-8") as arquivo:
        json.dump(revisao, arquivo, ensure_ascii=False, indent=2)

    return destino


def exibir_lista(titulo, itens):
    st.markdown(f"**{titulo}**")

    if not itens:
        st.write("Nenhum registro.")
        return

    for item in itens:
        st.write(f"• {item}")


st.set_page_config(
    page_title="Agente de Diárias — Revisão Humana",
    page_icon="📋",
    layout="wide",
)

st.title("Agente de Diárias")
st.caption("Instrução automatizada com revisão humana obrigatória")

resultados = carregar_resultados()

if not resultados:
    st.warning("Nenhum resultado de execução foi encontrado.")
    st.stop()

chaves = list(resultados)

selecionado = st.selectbox(
    "Selecione o pedido ou a execução",
    options=chaves,
)

registro = resultados[selecionado]
dados = registro["dados"]
instrucao = dados["instrucao"]

auditoria = (
    dados.get("auditoria_ferramentas")
    or dados.get("auditoria")
    or {}
)

barreira = (
    dados.get("barreira_validacao")
    or dados.get("validacao")
    or {}
)

st.divider()

col1, col2, col3, col4 = st.columns(4)

col1.metric("Pedido", instrucao.get("numero_pedido", "?"))

quantidade = instrucao.get("quantidade_diarias")
col2.metric(
    "Di\u00e1rias",
    str(quantidade) if quantidade is not None else "?",
)

valor = instrucao.get("valor_total")
valor_formatado = (
    f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if valor is not None
    else "?"
)
col3.metric("Valor total", valor_formatado)

recomendacao = instrucao.get("recomendacao", "?")
col4.metric(
    "Recomenda\u00e7\u00e3o",
    RECOMENDACOES.get(recomendacao, recomendacao),
)

st.write(
    "**Autorização superior exigida:**",
    "Sim" if instrucao.get("exige_autorizacao_superior") else "Não",
)

st.subheader("Verificações normativas")

verificacoes = instrucao.get("verificacoes") or []

for verificacao in verificacoes:
    criterio = verificacao.get("criterio", "")
    situacao = verificacao.get("situacao", "")

    with st.expander(
        f"{CRITERIOS.get(criterio, criterio)} — "
        f"{SITUACOES.get(situacao, situacao)}"
    ):
        st.write(verificacao.get("detalhe") or "Sem detalhe.")

col_pendencias, col_alertas = st.columns(2)

with col_pendencias:
    exibir_lista("Pendências", instrucao.get("pendencias") or [])

with col_alertas:
    exibir_lista("Alertas", instrucao.get("alertas") or [])

st.subheader("Auditoria e evidências")

aprovado = barreira.get("aprovado")

if aprovado is True:
    st.success("Barreira de validação aprovada.")
elif aprovado is False:
    st.error("Barreira de validação não aprovada.")
else:
    st.warning("Resultado da barreira não identificado.")

erros = barreira.get("erros") or []

if erros:
    exibir_lista("Problemas encontrados", erros)

with st.expander("Chamadas de ferramentas e evidências"):
    chamadas = auditoria.get("chamadas") or []

    if chamadas:
        for indice, chamada in enumerate(chamadas, start=1):
            nome = chamada.get("nome", f"Ferramenta {indice}")

            st.markdown(f"**{indice}. {nome}**")
            st.json(chamada)
    else:
        st.info(
            "Nenhuma chamada detalhada registrada neste resultado. "
            "Pedidos em diligência preliminar podem não executar ferramentas."
        )

with st.expander("Métricas da execução"):
    st.json(dados.get("metricas") or {})

st.divider()


st.subheader("Complementações e gestão de sessões")

with st.expander("Consultar complementações documentais"):
    from complementacoes import aplicar_complementacao

    numero_complementacao = st.selectbox(
        "Pedido com complementação",
        ["DIA-2026-0111", "DIA-2026-0112"],
        key="consulta_complementacao",
    )

    if st.button("Consultar complementação"):
        try:
            complemento = aplicar_complementacao(numero_complementacao)
        except (ValueError, KeyError, TypeError):
            st.error("N?o foi poss?vel validar a complementa??o.")
        else:
            st.success("Complementação validada.")
            st.write("Pedido:", complemento["numero_pedido"])
            st.json(complemento["alteracoes"])
            st.info("Consulta somente leitura. Nenhuma sess\u00e3o modificada.")

with st.expander("Consultar sessão persistida"):
    from persistencia_sessoes import obter_banco

    st.caption("Consulta somente leitura. Nenhuma exclus?o ser? executada.")

    if st.button("Consultar sessão selecionada"):
        try:
            banco = obter_banco()
            sessao = banco.get_session(
                session_id=instrucao["numero_pedido"],
                session_type="agent",
            )
        except Exception:
            st.error("N?o foi poss?vel consultar a sess?o.")
        else:
            if sessao is None:
                st.info("Nenhuma sess?o persistida encontrada.")
            else:
                st.success("Sess?o encontrada.")
                st.write("ID:", sessao.session_id)
                st.write(
                    "Usu?rio vinculado:",
                    "Sim" if sessao.user_id else "N?o",
                )

st.divider()

st.subheader("Revisão humana obrigatória")

with st.expander("Exclusao experimental de sessao e memorias"):
    import sqlite3
    from agno.db.sqlite import SqliteDb

    st.warning(
        "Esta operacao utiliza apenas uma copia experimental do SQLite. "
        "O banco principal, os JSONs e os backups nao serao apagados."
    )

    pasta_experimentos = BASE / "resultados" / "experimentos_memoria"
    banco_experimental = (
        pasta_experimentos / "cenario_C_teste_interface.db"
    )

    banco_fonte = pasta_experimentos / "cenario_C.db"
    numero_experimental = "DIA-2026-0101"

    st.write("Sessao experimental:", numero_experimental)

    if st.button(
        "Preparar copia experimental",
        key="preparar_copia_exclusao",
    ):
        try:
            if banco_experimental.exists():
                st.info(
                    "A copia experimental ja existe. "
                    "Nenhum arquivo foi sobrescrito."
                )
            elif not banco_fonte.is_file():
                st.error("Banco experimental de origem nao encontrado.")
            else:
                with sqlite3.connect(str(banco_fonte)) as fonte:
                    with sqlite3.connect(str(banco_experimental)) as copia:
                        fonte.backup(copia)

                st.success("Copia experimental preparada.")
        except (OSError, sqlite3.Error):
            st.error("Falha ao preparar a copia experimental.")

    confirmacao = st.checkbox(
        "Confirmo a exclusao somente na copia experimental",
        key="exclusao_experimental_confirmada",
    )

    texto_confirmacao = st.text_input(
        "Digite EXCLUIR para confirmar",
        key="texto_confirmacao_exclusao",
    )

    if st.button(
        "Excluir sessao e memorias da copia",
        disabled=not (
            confirmacao and texto_confirmacao == "EXCLUIR"
        ),
        key="executar_exclusao_experimental",
    ):
        if not banco_experimental.is_file():
            st.error("Prepare primeiro a copia experimental.")
        else:
            try:
                banco = SqliteDb(db_file=str(banco_experimental))

                sessao = banco.get_session(
                    session_id=numero_experimental,
                    session_type="agent",
                )

                if sessao is None:
                    st.warning(
                        "A sessao nao existe nesta copia. "
                        "Nenhuma exclusao realizada."
                    )
                else:
                    usuario = sessao.user_id

                    memorias = (
                        banco.get_user_memories(user_id=usuario)
                        if usuario
                        else []
                    ) or []

                    ids = [
                        memoria.memory_id
                        for memoria in memorias
                    ]

                    banco.delete_session(
                        session_id=numero_experimental
                    )

                    if ids:
                        banco.delete_user_memories(
                            memory_ids=ids,
                            user_id=usuario,
                        )

                    sessao_final = banco.get_session(
                        session_id=numero_experimental,
                        session_type="agent",
                    )

                    memorias_finais = (
                        banco.get_user_memories(user_id=usuario)
                        if usuario
                        else []
                    ) or []

                    with sqlite3.connect(
                        str(banco_experimental)
                    ) as conexao:
                        integridade = conexao.execute(
                            "PRAGMA integrity_check"
                        ).fetchone()[0]

                        contagens = {}

                        for tabela in (
                            "agno_sessions",
                            "agno_runs",
                            "agno_memories",
                        ):
                            existe = conexao.execute(
                                "SELECT COUNT(*) "
                                "FROM sqlite_master "
                                "WHERE type='table' AND name=?",
                                (tabela,),
                            ).fetchone()[0]

                            if existe:
                                contagens[tabela] = conexao.execute(
                                    f"SELECT COUNT(*) FROM {tabela}"
                                ).fetchone()[0]
                            else:
                                contagens[tabela] = 0

                    verificacoes = {
                        "Sessao excluida": sessao_final is None,
                        "Memorias excluidas": not memorias_finais,
                        "Sem sessoes residuais":
                            contagens["agno_sessions"] == 0,
                        "Sem execucoes residuais":
                            contagens["agno_runs"] == 0,
                        "Sem memorias residuais":
                            contagens["agno_memories"] == 0,
                        "SQLite integro": integridade == "ok",
                        "Banco principal preservado":
                            (BASE / "resultados" /
                             "agente_sessoes.db").is_file(),
                    }

                    st.write("Resultado da auditoria:")
                    st.json(verificacoes)

                    if all(verificacoes.values()):
                        st.success(
                            "Exclusao experimental verificada. "
                            "O banco principal nao foi alterado."
                        )
                    else:
                        st.error(
                            "Exclusao incompleta. "
                            "Consulte as verificacoes."
                        )

            except Exception:
                st.error(
                    "Falha na exclusao experimental. "
                    "O banco principal nao foi utilizado."
                )

st.divider()

revisao_existente = carregar_revisao(selecionado)

if revisao_existente:
    st.success("Este resultado já possui uma revisão humana registrada.")
    st.json(revisao_existente)
    st.stop()

if aprovado is not True:
    st.warning(
        "A barreira não foi aprovada ou não foi identificada. "
        "A revisão poderá registrar a pendência, mas não autorizar o pedido."
    )

with st.form(f"revisao_{selecionado}"):
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
        value=instrucao.get("minuta_despacho") or "",
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
        and instrucao.get("recomendacao") != "apto_para_autorizacao"
    ) or (
        decisao == "solicitar_diligencia"
        and instrucao.get("recomendacao") != "diligencia"
    ) or (
        decisao == "nao_autorizar"
        and instrucao.get("recomendacao") != "nao_recomendado"
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
            aprovado is not True
            or instrucao.get("recomendacao") != "apto_para_autorizacao"
            or instrucao.get("exige_autorizacao_superior")
        )
    ):
        st.error(
            "O encaminhamento está bloqueado: a barreira deve estar "
            "aprovada, a recomendação deve ser apta e não pode haver "
            "autorização superior pendente."
        )
    else:
        revisao = {
            "numero_pedido": instrucao.get("numero_pedido"),
            "arquivo_resultado": registro["arquivo"].name,
            "data_registro": datetime.now().astimezone().isoformat(),
            "revisor": revisor.strip(),
            "decisao_humana": decisao,
            "recomendacao_agente": instrucao.get("recomendacao"),
            "divergencia": divergencia,
            "justificativa": justificativa.strip(),
            "despacho_final": despacho.strip(),
            "barreira_aprovada": aprovado,
            "revisao_confirmada": True,
            "decisao_final_ordenador": False,
        }

        try:
            destino = salvar_revisao(selecionado, revisao)
        except FileExistsError:
            st.error(
                "Já existe uma revisão registrada. "
                "Nenhum arquivo foi sobrescrito."
            )
        else:
            st.success(
                f"Revisão humana registrada em {destino.name}. "
                "O encaminhamento não substitui a decisão do "
                "ordenador de despesa."
            )
