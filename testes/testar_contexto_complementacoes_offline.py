r"""Execute com .venv\Scripts\python.exe -B testes\testar_contexto_complementacoes_offline.py."""

import json
import re
import sqlite3
import socket
import sys
import tempfile
import unittest
from contextlib import ExitStack, closing
from copy import deepcopy
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PEDIDO_0111 = "DIA-2026-0111"
PEDIDO_0112 = "DIA-2026-0112"
MARCADOR_LOCAL = "MARCADOR_SINTETICO_DA_SESSAO_EM_TESTE"
MARCADOR_ALHEIO = "MARCADOR_SINTETICO_DE_OUTRA_SESSAO"


class ContextoComplementacoesOffline(unittest.TestCase):
    def setUp(self):
        self.assertEqual(version("agno"), "3.2.1")
        recursos = self.enterContext(ExitStack())
        self.caminho = Path(recursos.enter_context(tempfile.TemporaryDirectory())) / "sessoes.db"
        self.capturas = []
        self.tentativas_externas = []

        def bloquear_acesso(*args, **kwargs):
            self.tentativas_externas.append(True)
            raise AssertionError("Acesso externo bloqueado pelo teste.")

        self.addCleanup(self.assertFalse, self.tentativas_externas, "Houve tentativa de acesso externo.")
        for nome in ("connect", "connect_ex", "sendto", "send", "sendall"):
            recursos.enter_context(patch.object(socket.socket, nome, bloquear_acesso))
        for nome in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
            recursos.enter_context(patch.object(socket, nome, bloquear_acesso))
        recursos.enter_context(patch("dotenv.load_dotenv", return_value=False))

        import agente
        import complementacoes
        import execucao_interativa
        import persistencia_sessoes
        from agno.models.response import ModelResponse

        capturas = self.capturas

        class ModeloSimulado(agente.OpenAIResponses):
            def invoke(self, messages, **kwargs):
                execucao = kwargs["run_response"]
                capturas.append((execucao.session_id, execucao.user_id, deepcopy(messages)))
                # A saída vazia não tem mérito. O teste observa somente o contexto recebido.
                return ModelResponse()

        sqlite_agno = agente.SqliteDb

        def abrir_banco_temporario(*, db_file):
            self.assertEqual(Path(db_file), self.caminho)
            banco = sqlite_agno(db_file=db_file)
            recursos.callback(banco.close)
            return banco

        for nome in ("get_client", "get_async_client"):
            recursos.enter_context(patch.object(agente.OpenAIResponses, nome, bloquear_acesso))
        recursos.enter_context(patch.object(agente, "OpenAIResponses", ModeloSimulado))
        recursos.enter_context(patch.object(agente, "SqliteDb", abrir_banco_temporario))
        self.complementacoes = complementacoes
        self.servico = execucao_interativa
        self.persistencia = persistencia_sessoes

    def preparar(self, protocolo, campo):
        diligencia = self.persistencia.registrar_diligencia(protocolo, caminho_banco=self.caminho)
        self.assertIsNone(diligencia.user_id)
        acervo = self.complementacoes.aplicar_complementacao(protocolo)
        valor = acervo["pedido_corrigido"][campo]
        sessao = self.persistencia.registrar_complementacao(
            protocolo, {campo: valor}, caminho_banco=self.caminho,
        )
        preparado = self.persistencia.preparar_pedido_complementado(protocolo, caminho_banco=self.caminho)
        self.assertEqual(diligencia.session_id, protocolo)
        self.assertEqual(sessao.session_id, protocolo)
        self.assertEqual(preparado["session_id"], protocolo)
        self.assertEqual(sessao.user_id, preparado["user_id"])
        eventos = sessao.metadata["eventos_administrativos"]
        self.assertEqual([evento["tipo"] for evento in eventos], ["diligencia_preliminar", "complementacao"])
        chave_evento = "matricula_validada" if campo == "matricula" else campo
        self.assertTrue(eventos[-1]["dados"][chave_evento] == valor, "Evento sem a correção validada.")
        self.assertTrue(preparado["pedido_corrigido"][campo] == valor, "Correção não recuperada.")
        return preparado, eventos

    def retomar(self, preparado):
        return self.servico.executar_tentativa(
            protocolo=preparado["session_id"],
            tentativa_id=str(uuid4()),
            pedido=preparado["pedido_corrigido"],
            session_id=preparado["session_id"],
            user_id=preparado["user_id"],
            usar_memoria=True,
            caminho_banco=self.caminho,
        )

    def capturar_retomada(self, preparado):
        self.retomar(preparado)
        self.assertEqual(len(self.capturas), 1, "A retomada deve chegar ao modelo simulado uma vez.")
        protocolo, titular, mensagens = self.capturas[0]
        self.assertEqual(protocolo, preparado["session_id"])
        self.assertTrue(titular == preparado["user_id"], "Titular divergente na chamada ao modelo.")
        return mensagens

    def verificar_primeira_retomada(self, mensagens, eventos):
        self.assertEqual([mensagem.role for mensagem in mensagens], ["system", "user"])
        self.assertFalse(any(mensagem.from_history for mensagem in mensagens))
        texto = "\n".join(mensagem.get_content_string() for mensagem in mensagens)
        for evento in eventos:
            self.assertTrue(evento["tipo"] not in texto, "Tipo de evento administrativo chegou ao modelo.")
            self.assertTrue(evento["registrado_em"] not in texto, "Registro administrativo chegou ao modelo.")
        self.assertTrue("eventos_administrativos" not in texto, "Metadados chegaram ao modelo.")
        return json.loads(mensagens[-1].content), texto

    def inserir_execucao(self, preparado, titular, marcador):
        from agno.models.message import Message
        from agno.run.agent import RunOutput, RunStatus

        protocolo = preparado["session_id"]
        execucao = RunOutput(
            run_id=str(uuid4()),
            session_id=protocolo,
            agent_id="agente_diarias",
            user_id=titular,
            status=RunStatus.completed,
            messages=[Message(role="user", content=marcador)],
        )
        banco = self.persistencia.obter_banco(self.caminho)
        try:
            banco.upsert_run(execucao, session_id=protocolo, user_id=titular)
            gravada = banco.get_run(execucao.run_id, deserialize=False)
            self.assertIsNotNone(gravada, "A execução sintética precisa estar gravada.")
        finally:
            banco.close()

    def test_a_retorno_corrigido_com_resumo_administrativo(self):
        preparado, eventos = self.preparar(PEDIDO_0111, "data_retorno")
        mensagens = self.capturar_retomada(preparado)
        pedido, _ = self.verificar_primeira_retomada(mensagens, eventos)
        self.assertTrue(pedido["data_retorno"] == preparado["pedido_corrigido"]["data_retorno"])
        self.assertEqual(pedido["resumo_administrativo"], {
            "motivo_diligencia": "data_retorno_ausente",
            "data_retorno_corrigida_e_validada": True,
        })
        self.assertNotIn("justificativa", pedido)
        self.assertNotIn("resumo_administrativo", mensagens[0].content)

    def test_b_titular_corrigido_sem_matricula_invalida(self):
        preparado, eventos = self.preparar(PEDIDO_0112, "matricula")
        mensagens = self.capturar_retomada(preparado)
        pedido, texto = self.verificar_primeira_retomada(mensagens, eventos)
        invalida = self.complementacoes.obter_pedido(PEDIDO_0112)["matricula"]
        self.assertTrue(pedido["matricula"] == preparado["user_id"])
        self.assertTrue(invalida not in texto, "A matrícula indevida chegou ao modelo.")
        self.assertEqual(pedido["resumo_administrativo"], {
            "motivo_diligencia": "divergencia_cadastral",
            "matricula_corrigida_e_validada": True,
            "titular_atual_conferido_no_cadastro": True,
        })
        self.assertNotIn("justificativa", pedido)
        self.assertNotIn("resumo_administrativo", mensagens[0].content)

    def test_c_replay_de_mensagem_elegivel(self):
        preparado, _ = self.preparar(PEDIDO_0111, "data_retorno")
        self.inserir_execucao(preparado, preparado["user_id"], MARCADOR_LOCAL)
        mensagens = self.capturar_retomada(preparado)
        replay = [mensagem for mensagem in mensagens if mensagem.content == MARCADOR_LOCAL]
        self.assertEqual(len(replay), 1)
        self.assertTrue(replay[0].from_history)

    def test_d_isolamento_entre_sessoes(self):
        alvo, _ = self.preparar(PEDIDO_0111, "data_retorno")
        outra, _ = self.preparar(PEDIDO_0112, "matricula")
        self.inserir_execucao(alvo, alvo["user_id"], MARCADOR_LOCAL)
        self.inserir_execucao(outra, outra["user_id"], MARCADOR_ALHEIO)
        mensagens = self.capturar_retomada(alvo)
        texto = "\n".join(mensagem.get_content_string() for mensagem in mensagens)
        self.assertTrue(MARCADOR_LOCAL in texto, "O controle positivo precisa aparecer na sessão alvo.")
        self.assertTrue(MARCADOR_ALHEIO not in texto, "O marcador de outra sessão chegou ao modelo.")
        self.assertNotIn("divergencia_cadastral", texto)
        self.assertTrue(outra["user_id"] not in texto, "Titular de outra sessão chegou ao modelo.")

    def test_e_recusa_execucao_legada_com_titular_incompativel(self):
        preparado, _ = self.preparar(PEDIDO_0112, "matricula")
        invalida = self.complementacoes.obter_pedido(PEDIDO_0112)["matricula"]
        self.assertTrue(invalida != preparado["user_id"])
        self.inserir_execucao(preparado, invalida, MARCADOR_ALHEIO)
        with self.assertRaisesRegex(ValueError, "execucoes incompativeis"):
            self.persistencia.preparar_pedido_complementado(PEDIDO_0112, caminho_banco=self.caminho)
        self.assertEqual(self.retomar(preparado)["status"], "analise_manual")
        self.assertEqual(self.capturas, [])

    def test_f_recusa_eventos_adulterados_incompletos_ou_incompativeis(self):
        preparado, eventos = self.preparar(PEDIDO_0111, "data_retorno")
        casos = (
            ("diligencia adulterada", 0, {"pendencias": [MARCADOR_ALHEIO]}),
            ("complementacao incompleta", 1, {"pedido_apto_para_analise": True}),
            ("campo incompativel", 1, {"matricula_validada": "000001", "pedido_apto_para_analise": True}),
            ("texto extra", 1, {**eventos[1]["dados"], "texto": MARCADOR_ALHEIO}),
        )
        banco = self.persistencia.obter_banco(self.caminho)
        self.addCleanup(banco.close)
        tabela = banco._get_table("sessions")
        for nome, indice, dados in casos:
            with self.subTest(nome=nome):
                adulterados = deepcopy(eventos)
                adulterados[indice]["dados"] = dados
                metadata = {
                    "numero_pedido": PEDIDO_0111,
                    "estado": "complementado",
                    "eventos_administrativos": adulterados,
                }
                with banco.db_engine.begin() as conexao:
                    conexao.execute(
                        tabela.update().where(tabela.c.session_id == PEDIDO_0111).values(metadata=metadata)
                    )
                with self.assertRaises(ValueError):
                    self.persistencia.preparar_pedido_complementado(PEDIDO_0111, caminho_banco=self.caminho)
                self.assertEqual(self.retomar(preparado)["status"], "analise_manual")
                self.assertEqual(self.capturas, [])
    def test_g_pedido_comum_sem_resumo_administrativo(self):
        self.preparar(PEDIDO_0111, "data_retorno")
        protocolo = "DIA-2026-0101"
        pedido = self.complementacoes.obter_pedido(protocolo)
        mensagens = self.capturar_retomada({
            "session_id": protocolo, "user_id": pedido["matricula"], "pedido_corrigido": pedido,
        })
        self.assertEqual([mensagem.role for mensagem in mensagens], ["system", "user"])
        entrada = json.loads(mensagens[-1].content)
        self.assertNotIn("resumo_administrativo", entrada)
        self.assertIn("justificativa", entrada)

    def test_privacidade_0104_no_modelo_e_no_sqlite(self):
        from seguranca import PADROES_SENSIVEIS

        protocolo = "DIA-2026-0104"
        pedido = self.complementacoes.obter_pedido(protocolo)
        sensiveis = []
        for chave in ("cpf", "conta_bancaria", "agencia_bancaria"):
            sensiveis.extend(
                re.sub(r"[^0-9]", "", trecho)
                for trecho in re.findall(PADROES_SENSIVEIS[chave], pedido["justificativa"])
            )
        self.assertGreaterEqual(len(sensiveis), 2)
        preparado = {"session_id": protocolo, "user_id": pedido["matricula"], "pedido_corrigido": pedido}
        mensagens = self.capturar_retomada(preparado)
        entrada = json.loads(next(m.content for m in mensagens if m.role == "user"))
        campos = ("numero", "matricula", "data_pedido", "data_partida", "data_retorno")
        for campo in campos:
            self.assertTrue(entrada[campo] == pedido[campo], f"Identificador operacional alterado: {campo}.")

        def conferir_sem_dados_brutos(texto):
            # Detecta os números sintéticos inclusive com os separadores removidos.
            for sensivel in sensiveis:
                padrao = r"(?<![0-9])" + r"[.\s-]*".join(sensivel) + r"(?![0-9])"
                self.assertFalse(re.search(padrao, texto), "Número sensível sintético encontrado.")

        conferir_sem_dados_brutos("\n".join(m.get_content_string() for m in mensagens))
        uri = self.caminho.as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as conexao:
            tabelas = [nome for (nome,) in conexao.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table' AND name NOT GLOB 'sqlite_*'"
            )]
            self.assertIn("agno_sessions", tabelas)
            self.assertIn("agno_runs", tabelas)
            persistidas = conexao.execute("SELECT run_data FROM agno_runs WHERE session_id = ?", (protocolo,)).fetchall()
            self.assertEqual(len(persistidas), 1)
            for campo in campos:
                self.assertTrue(pedido[campo] in persistidas[0][0], f"Campo operacional ausente: {campo}.")
            for tabela in tabelas:
                identificador = '"' + tabela.replace('"', '""') + '"'
                for linha in conexao.execute(f"SELECT * FROM {identificador}"):
                    for valor in linha:
                        if isinstance(valor, str):
                            conferir_sem_dados_brutos(valor)

    def test_h_recusa_pedido_alterado_depois_da_recuperacao(self):
        preparado, _ = self.preparar(PEDIDO_0111, "data_retorno")
        pedido = preparado["pedido_corrigido"]
        # Uma data operacionalmente válida ainda precisa corresponder ao registro persistido.
        pedido["data_retorno"] = pedido["data_partida"]
        self.assertEqual(self.retomar(preparado)["status"], "analise_manual")
        self.assertEqual(self.capturas, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
