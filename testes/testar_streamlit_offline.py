"""Exercita o Streamlit com SQLite descartável e a fronteira OIDC simulada."""

import json
import os
import secrets
import socket
import sqlite3
import sys
import tempfile
import unittest
from contextlib import ExitStack, closing
from contextvars import ContextVar
from pathlib import Path
from time import time
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

MODO_EXCLUSAO = "Excluir memória e histórico do agente"
EMISSOR = "https://oidc.exemplo.invalid"
ALVO = "990871"
OUTRO = "990872"
MARCADOR = "CONTEUDO_SINTETICO_PRIVADO"
CPF_SINTETICO = "000.000.000-00"
CONTA_SINTETICA = "conta 000000-0"


class StreamlitOffline(unittest.TestCase):
    def setUp(self):
        self.recursos = self.enterContext(ExitStack())
        pasta = self.recursos.enter_context(tempfile.TemporaryDirectory())
        self.banco = Path(pasta).resolve() / "streamlit.db"
        self.chave = secrets.token_hex(32)
        self.usuario = {}
        self.chamadas = []
        tentativas = []

        def negar(*args, **kwargs):
            tentativas.append(True)
            raise AssertionError("Operação externa bloqueada.")

        self.recursos.callback(lambda: self.assertFalse(tentativas, "Houve tentativa de acesso externo."))
        em_socketpair = ContextVar("em_socketpair", default=False)
        socketpair = socket.socketpair
        conectar = socket.socket.connect

        def socketpair_local(*args, **kwargs):
            # O asyncio no Windows usa um par local para sinalização interna.
            token = em_socketpair.set(True)
            try:
                return socketpair(*args, **kwargs)
            finally:
                em_socketpair.reset(token)

        def conectar_apenas_socketpair(sock, endereco):
            if em_socketpair.get() and isinstance(endereco, tuple) and endereco[0] in {"127.0.0.1", "::1"}:
                return conectar(sock, endereco)
            return negar(sock, endereco)

        self.recursos.enter_context(patch.object(socket, "socketpair", socketpair_local))
        self.recursos.enter_context(patch.object(socket.socket, "connect", conectar_apenas_socketpair))
        for nome in ("connect_ex", "sendto"):
            self.recursos.enter_context(patch.object(socket.socket, nome, negar))
        for nome in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
            self.recursos.enter_context(patch.object(socket, nome, negar))
        for nome in ("openai.OpenAI.__init__", "openai.AsyncOpenAI.__init__"):
            self.recursos.enter_context(patch(nome, negar))
        self.recursos.enter_context(patch("dotenv.load_dotenv", return_value=False))
        self.recursos.enter_context(patch.dict(os.environ, {
            "BARREIRA_HMAC_CHAVE_HEX": "", "TITULARES_OIDC_JSON": "",
        }))

        import agente
        import streamlit
        from agno.models.response import ModelResponse
        from streamlit.testing.v1 import AppTest

        capturas = self.chamadas

        class ModeloOffline(agente.OpenAIResponses):
            def invoke(self, messages, **kwargs):
                run = kwargs["run_response"]
                capturas.append((run.session_id, run.user_id, run.run_id))
                return ModelResponse()

        self.AppTest = AppTest
        self.recursos.enter_context(patch.object(agente, "OpenAIResponses", ModeloOffline))
        self.recursos.enter_context(patch.object(streamlit, "user", self.usuario))
        self.recursos.enter_context(patch.object(streamlit, "login", negar))
        self.recursos.enter_context(patch("barreira_persistente._TRABALHO", self.banco))

    def configurar(self, *titulares):
        os.environ["BARREIRA_HMAC_CHAVE_HEX"] = self.chave
        os.environ["TITULARES_OIDC_JSON"] = json.dumps([
            {"iss": EMISSOR, "sub": sujeito, "matricula": matricula, "protocolos": protocolos}
            for sujeito, matricula, protocolos in titulares
        ])

    def autenticar(self, sujeito, *, emissor=EMISSOR, validade=3600):
        self.usuario.clear()
        self.usuario.update(is_logged_in=True, iss=emissor, sub=sujeito, exp=int(time()) + validade)

    def executar(self, app=None):
        app = app if app is not None else self.AppTest.from_file(str(BASE / "app.py"))
        app.run(timeout=45)
        self.assertEqual(len(app.exception), 0, "O Streamlit apresentou uma exceção.")
        return app

    def clicar(self, app, rotulo):
        botao = next(botao for botao in app.button if botao.label == rotulo)
        botao.click()
        return self.executar(app)

    def modo(self, app, modo):
        app.radio[0].set_value(modo)
        return self.executar(app)

    def texto(self, app):
        return "\n".join(
            item.value for categoria in (
                app.markdown, app.info, app.warning, app.error, app.success, app.caption, app.subheader,
            )
            for item in categoria
        )

    def registros(self, titular):
        with closing(sqlite3.connect(self.banco.as_uri() + "?mode=ro", uri=True)) as conexao:
            return tuple(conexao.execute(f"SELECT * FROM {tabela} WHERE user_id = ?", (titular,)).fetchall()
                         for tabela in ("agno_sessions", "agno_runs", "agno_memories"))

    def preparar_registros(self):
        from agno.db.schemas.memory import UserMemory
        from agno.db.sqlite import SqliteDb
        from agno.run.agent import RunOutput, RunStatus
        from agno.session.agent import AgentSession

        with closing(SqliteDb(db_file=str(self.banco))) as banco:
            for protocolo, titular in (("DIA-2026-0101", ALVO), ("DIA-2026-0102", OUTRO)):
                banco.upsert_session(AgentSession(
                    session_id=protocolo, user_id=titular,
                    metadata={"marcador": MARCADOR, "cpf_sintetico": CPF_SINTETICO, "conta": CONTA_SINTETICA},
                ))
                banco.upsert_run(RunOutput(
                    run_id=protocolo, session_id=protocolo, user_id=titular, status=RunStatus.completed,
                ), session_id=protocolo, user_id=titular)
                banco.upsert_user_memory(UserMemory(memory_id=protocolo, user_id=titular, memory=MARCADOR))

    def test_configuracao_ausente_e_autenticacao_obrigatoria(self):
        self.autenticar("titular-a")
        app = self.modo(self.executar(), MODO_EXCLUSAO)
        self.assertIn("chave HMAC estável", self.texto(app))
        self.assertFalse(app.checkbox)
        self.assertFalse(self.banco.exists())

        self.configurar(("titular-a", ALVO, ["DIA-2026-0101"]))
        self.usuario.update(is_logged_in=False, matricula=ALVO)
        app = self.executar(app)
        self.assertIn("Autenticação do titular obrigatória", self.texto(app))
        self.assertFalse(app.checkbox)
        self.assertFalse(self.banco.exists())
        self.autenticar("titular-a", emissor="https://outro.exemplo.invalid")
        app = self.executar(app)
        self.assertIn("vínculo de titular autorizado", self.texto(app))
        self.assertFalse(self.banco.exists())
        self.autenticar("titular-a", validade=-60)
        app = self.executar(app)
        self.assertIn("Autenticação do titular obrigatória", self.texto(app))
        self.assertFalse(self.banco.exists())
        self.assertFalse(self.chamadas)

    def test_exclusao_confirmada_so_para_identidade_autenticada(self):
        from agno.db.schemas.memory import UserMemory
        from barreira_persistente import BarreiraPersistente
        from sqlalchemy.exc import IntegrityError

        self.preparar_registros()
        self.configurar(("titular-a", ALVO, ["DIA-2026-0101"]), ("titular-b", OUTRO, ["DIA-2026-0102"]))
        self.autenticar("titular-a")
        app = self.executar()
        self.assertEqual(app.selectbox[0].options, ["DIA-2026-0101"])
        antes_a, antes_b = self.registros(ALVO), self.registros(OUTRO)
        self.assertEqual(tuple(map(len, antes_a)), (1, 1, 1))
        app = self.modo(app, MODO_EXCLUSAO)
        self.assertEqual(len(app.text_input), 0)
        app.session_state["matricula_para_excluir"] = OUTRO
        app.query_params["matricula"] = OUTRO
        app = self.clicar(app, "Solicitar exclusão")
        self.assertIn("Confirme explicitamente", self.texto(app))
        self.assertTrue(self.registros(ALVO) == antes_a)
        self.assertTrue(self.registros(OUTRO) == antes_b)

        barreira = BarreiraPersistente(bytes.fromhex(self.chave))
        with barreira.abrir_agno(ALVO, caminho_banco=self.banco, banco_autorizado=self.banco) as antigo:
            app.checkbox[0].check()
            app = self.clicar(app, "Solicitar exclusão")
            self.assertIn("Exclusão lógica executada", self.texto(app))
            self.assertIn("bloqueio de novas gravações foi confirmado", self.texto(app))
            self.assertIn("Antes · Sessões · 1", self.texto(app))
            self.assertIn("Depois · Sessões · 0", self.texto(app))
            with self.assertRaisesRegex(IntegrityError, "barreira_bloqueada"):
                antigo.upsert_user_memory(UserMemory(user_id=ALVO, memory=MARCADOR))
        self.assertEqual(tuple(map(len, self.registros(ALVO))), (0, 0, 0))
        self.assertTrue(self.registros(OUTRO) == antes_b)
        tela = self.texto(app)
        self.assertFalse(any(valor in tela for valor in (
            ALVO, OUTRO, MARCADOR, CPF_SINTETICO, CONTA_SINTETICA, self.chave,
        )))
        app = self.modo(app, "Executar pedido")
        self.assertIn("Novas gravações estão bloqueadas", self.texto(app))
        self.assertFalse(app.selectbox)
        self.autenticar("titular-b")
        app = self.executar(app)
        self.assertEqual(app.selectbox[0].options, ["DIA-2026-0102"])
        self.assertFalse(self.chamadas)

    def test_0111_e_0112_preservam_diligencia_complementacao_e_retomada(self):
        from complementacoes import aplicar_complementacao
        from persistencia_sessoes import preparar_pedido_complementado

        protocolos = ("DIA-2026-0111", "DIA-2026-0112")
        pedidos = [aplicar_complementacao(protocolo)["pedido_corrigido"] for protocolo in protocolos]
        self.configurar(*[(f"titular-{i}", pedido["matricula"], [pedido["numero"]])
                          for i, pedido in enumerate(pedidos)])
        for i, pedido in enumerate(pedidos):
            with self.subTest(protocolo=pedido["numero"]):
                self.autenticar(f"titular-{i}")
                app = self.executar()
                protocolo, titular = pedido["numero"], pedido["matricula"]
                self.assertEqual(app.selectbox[0].options, [protocolo])
                app = self.clicar(app, "Executar análise")
                self.assertIn("Diligência preliminar", self.texto(app))
                campo = "data_retorno" if i == 0 else "matricula"
                rotulo = "Data de retorno corrigida" if i == 0 else "Matrícula corrigida"
                if i == 1:
                    next(item for item in app.text_input if item.label == rotulo).set_value(pedidos[0]["matricula"])
                    app = self.clicar(app, "Registrar complementação")
                    with self.assertRaises(ValueError):
                        preparar_pedido_complementado(protocolo, caminho_banco=self.banco)
                next(item for item in app.text_input if item.label == rotulo).set_value(pedido[campo])
                app = self.clicar(app, "Registrar complementação")
                preparado = preparar_pedido_complementado(protocolo, caminho_banco=self.banco)
                self.assertEqual(preparado["session_id"], protocolo)
                self.assertTrue(preparado["user_id"] == titular)
                self.assertTrue(preparado["pedido_corrigido"][campo] == pedido[campo])
                self.clicar(app, "Retomar análise complementada")
                self.assertEqual(len(self.chamadas), i + 1)
                self.assertTrue(self.chamadas[-1][:2] == (protocolo, titular))
                self.assertEqual(len(self.registros(titular)[1]), 1)

    def test_falha_exibe_revisao_e_mantem_bloqueio_confirmado(self):
        self.preparar_registros()
        self.configurar(("titular-a", ALVO, ["DIA-2026-0101"]))
        self.autenticar("titular-a")
        app = self.modo(self.executar(), MODO_EXCLUSAO)
        antes = self.registros(ALVO)
        app.checkbox[0].check()
        with patch("exclusao_memoria._excluir", side_effect=RuntimeError(MARCADOR)):
            app = self.clicar(app, "Solicitar exclusão")
        tela = self.texto(app)
        self.assertIn("Revisão manual necessária", tela)
        self.assertIn("bloqueio de novas gravações foi confirmado", tela)
        self.assertNotIn(MARCADOR, tela)
        self.assertTrue(self.registros(ALVO) == antes)
        app = self.modo(app, "Executar pedido")
        self.assertIn("Novas gravações estão bloqueadas", self.texto(app))
        self.assertFalse(self.chamadas)

    def test_chave_diferente_da_chave_do_banco_recusa_operacoes(self):
        self.preparar_registros()
        self.configurar(("titular-a", ALVO, ["DIA-2026-0101"]))
        self.autenticar("titular-a")
        app = self.executar()
        antes = self.registros(ALVO)
        chave_incompativel = secrets.token_hex(32)
        os.environ["BARREIRA_HMAC_CHAVE_HEX"] = chave_incompativel
        app = self.executar(app)
        self.assertIn("Banco de trabalho indisponível", self.texto(app))
        self.assertFalse(app.selectbox)
        app = self.modo(app, MODO_EXCLUSAO)
        app.checkbox[0].check()
        app = self.clicar(app, "Solicitar exclusão")
        tela = self.texto(app)
        self.assertIn("Solicitação bloqueada", tela)
        self.assertNotIn("bloqueio de novas gravações foi confirmado", tela)
        self.assertFalse(any(valor in tela for valor in (chave_incompativel, self.chave)))
        self.assertTrue(self.registros(ALVO) == antes)

    def test_consultas_reais_da_trilha_aparecem_so_apos_aprovacao(self):
        import agente
        from agno.models.response import ModelResponse
        from barreira_validacao import _encaminhamento, _produzir_instrucao
        from complementacoes import obter_pedido
        from execucao_interativa import consultas_publicaveis
        from validacao_normativa import obter_evidencias_normativas

        protocolo = "DIA-2026-0101"
        pedido = obter_pedido(protocolo)
        titular = pedido["matricula"]
        self.configurar(("titular-a", titular, [protocolo]))
        self.autenticar("titular-a")
        evidencias = obter_evidencias_normativas(pedido)
        instrucao = _produzir_instrucao(pedido, evidencias, _encaminhamento(pedido, evidencias))
        ordem = ("verificar_cadastro", "verificar_prestacoes", "verificar_calculo", "verificar_orcamento")
        nomes = []

        class ModeloComFerramentas(agente.OpenAIResponses):
            def invoke(self, messages, **kwargs):
                passo = sum(m.role == "tool" and not m.from_history for m in messages)
                if passo == len(ordem):
                    return ModelResponse(content=instrucao.model_dump_json())
                nome = ordem[passo]
                nomes.append(nome)
                return ModelResponse(tool_calls=[{
                    "id": f"call_teste_{passo}", "type": "function",
                    "function": {"name": nome, "arguments": "{}"},
                }])

        auditada = {"chamadas_python": [{
            "ferramenta_agno": "verificar_cadastro", "nome": "consultar_servidor", "erro": False,
            "argumentos": {"matricula": titular, "cpf": CPF_SINTETICO, "conta": CONTA_SINTETICA, "segredo": MARCADOR},
        }]}
        projetadas = consultas_publicaveis(auditada, titular)
        self.assertEqual(list(projetadas[0]["argumentos"]), ["matricula"])
        with patch.object(agente, "OpenAIResponses", ModeloComFerramentas):
            app = self.clicar(self.executar(), "Executar análise")
        self.assertEqual(tuple(nomes), ordem)
        self.assertIn("Consultas executadas", self.texto(app))
        self.assertTrue(any(x.label == "verificar_orcamento · consultar_saldo" for x in app.expander))
        textos = "\n".join(x.value for x in app.text)
        self.assertIn("valor_solicitado · 980.0", textos)
        self.assertIn(f"data_partida · {pedido['data_partida']}", textos)
        self.assertFalse(any(v in textos for v in (CPF_SINTETICO, CONTA_SINTETICA, MARCADOR)))

        class ModeloRecusado(ModeloComFerramentas):
            def invoke(self, messages, **kwargs):
                return ModelResponse(content=instrucao.model_dump_json())

        with patch.object(agente, "OpenAIResponses", ModeloRecusado):
            app = self.clicar(app, "Executar análise")
        self.assertNotIn("Consultas executadas", self.texto(app))
        self.assertFalse(any(x.label.startswith("verificar_") for x in app.expander))
        self.assertTrue(app.error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
