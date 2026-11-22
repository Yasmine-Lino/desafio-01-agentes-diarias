"""Protótipo de contrato em SQLite descartável. Não instala a barreira no aplicativo."""

import hashlib
import hmac
import multiprocessing
import secrets
import socket
import sqlite3
import sys
import tempfile
import unittest
from contextlib import ExitStack, closing, contextmanager
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ALVO = "990651"
OUTRO = "990652"
TABELAS = {
    "agno_sessions": ("session_id", True),
    "agno_runs": ("run_id", True),
    "agno_memories": ("memory_id", False),
}


def chave(segredo, titular):
    return hmac.digest(segredo, b"barreira-teste:" + titular.encode("ascii"), "sha256")


def conectar(caminho, segredo, titular=None, geracao=None):
    """A autorização da conexão permanece vinculada à geração capturada na admissão."""
    conexao = sqlite3.connect(caminho.as_uri() + "?mode=rw", uri=True, timeout=0)
    conexao.execute("PRAGMA foreign_keys = ON")
    autorizado = chave(segredo, titular) if titular is not None else None
    conexao.create_function("chave_titular", 1, lambda valor: chave(segredo, valor) if valor else None)
    conexao.create_function("geracao_operacao", 1, lambda token: geracao if token == autorizado else None)
    return conexao


def instalar_prototipo(conexao):
    conexao.executescript("""
        CREATE TABLE restricoes (
            chave BLOB PRIMARY KEY, geracao INTEGER NOT NULL,
            estado TEXT NOT NULL CHECK (estado IN ('ativo', 'bloqueio_pendente', 'excluido'))
        );
        CREATE TABLE vinculos (
            protocolo TEXT PRIMARY KEY, chave BLOB NOT NULL REFERENCES restricoes(chave)
        );
    """)
    for tabela, (identificador, tem_protocolo) in TABELAS.items():
        for operacao in ("INSERT", "UPDATE"):
            verificacoes = []
            for registro in ("NEW", "OLD") if operacao == "UPDATE" else ("NEW",):
                chave_titular = f"chave_titular({registro}.user_id)"
                if tem_protocolo:
                    vinculo = f"(SELECT chave FROM vinculos WHERE protocolo = {registro}.session_id)"
                    if tabela == "agno_sessions":
                        verificacoes.append(
                            f"SELECT CASE WHEN {vinculo} IS NOT NULL AND {registro}.user_id IS NOT NULL "
                            f"AND {vinculo} IS NOT {chave_titular} THEN RAISE(ABORT, 'vinculo_incompativel') END;"
                        )
                        chave_titular = f"COALESCE({chave_titular}, {vinculo})"
                    else:
                        verificacoes.append(
                            "SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM agno_sessions s "
                            f"WHERE s.session_id = {registro}.session_id AND s.user_id = {registro}.user_id) "
                            "THEN RAISE(ABORT, 'vinculo_incompativel') END;"
                        )
                verificacoes.append(
                    f"SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM restricoes r WHERE r.chave = {chave_titular} "
                    "AND r.estado = 'ativo' AND r.geracao = geracao_operacao(r.chave)) "
                    "THEN RAISE(ABORT, 'barreira_persistente') END;"
                )
            if operacao == "INSERT":
                # Impede substituir por UPSERT/REPLACE um ID pertencente a outro titular.
                verificacoes.append(
                    f"SELECT CASE WHEN EXISTS (SELECT 1 FROM {tabela} existente "
                    f"WHERE existente.{identificador} = NEW.{identificador} "
                    "AND existente.user_id IS NOT NEW.user_id) "
                    "THEN RAISE(ABORT, 'vinculo_incompativel') END;"
                )
            corpo = " ".join(verificacoes)
            conexao.execute(
                f"CREATE TRIGGER proteger_{tabela}_{operacao.lower()} BEFORE {operacao} ON {tabela} BEGIN {corpo} END"
            )


def gravar_sessao(conexao, protocolo, titular, metadata="{}"):
    conexao.execute(
        "INSERT INTO agno_sessions (session_id, session_type, user_id, created_at, metadata) "
        "VALUES (?, 'agent', ?, 1, ?)",
        (protocolo, titular, metadata),
    )


def escritor_independente(caminho, segredo, protocolo, manter_reserva, canal):
    """Processo filho da corrida. Usa somente sqlite3 e o arquivo temporário."""
    try:
        with canal, closing(conectar(caminho, segredo, ALVO, 1)) as conexao:
            try:
                conexao.execute("BEGIN IMMEDIATE")
                gravar_sessao(conexao, protocolo, ALVO)
                if manter_reserva:
                    canal.send("escrita_reservada")
                    if not canal.poll(15) or canal.recv() != "confirmar":
                        raise RuntimeError("Sincronização do experimento falhou.")
                conexao.commit()
                canal.send("gravado")
            except sqlite3.IntegrityError as erro:
                conexao.rollback()
                canal.send("bloqueado" if str(erro) == "barreira_persistente" else "erro_inesperado")
    finally:
        canal.close()


def escritor_producao(caminho, segredo, canal):
    from barreira_persistente import BarreiraPersistente
    from sqlalchemy.exc import IntegrityError

    # O trabalhador já tinha uma autorização capturada quando a exclusão começou.
    barreira = BarreiraPersistente(segredo)
    engine = barreira._engine(caminho, admitido=barreira._chave("titular", ALVO))
    with canal:
        try:
            with engine.begin() as conexao:
                conexao.exec_driver_sql(
                    "INSERT INTO agno_sessions (session_id, session_type, user_id, created_at) "
                    "VALUES ('tardio-processo', 'agent', ?, 1)", (ALVO,),
                )
        except IntegrityError as erro:
            canal.send(str(erro.orig) == "barreira_bloqueada")
        else:
            canal.send(False)
        finally:
            engine.dispose()


class BarreiraPersistenteOffline(unittest.TestCase):
    def setUp(self):
        self.assertEqual(version("agno"), "3.2.1")
        recursos = self.enterContext(ExitStack())
        pasta = recursos.enter_context(tempfile.TemporaryDirectory())
        self.caminho = Path(pasta).resolve() / "contrato.db"
        self.segredo = secrets.token_bytes(32)
        tentativas = []

        def negar(*args, **kwargs):
            tentativas.append(True)
            raise AssertionError("Acesso externo bloqueado.")

        recursos.callback(lambda: self.assertFalse(tentativas, "Houve tentativa de acesso externo."))
        for nome in ("connect", "connect_ex", "send", "sendall", "sendto"):
            recursos.enter_context(patch.object(socket.socket, nome, negar))
        for nome in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
            recursos.enter_context(patch.object(socket, nome, negar))
        for nome in ("openai.OpenAI.__init__", "openai.AsyncOpenAI.__init__", "dotenv.load_dotenv"):
            recursos.enter_context(patch(nome, negar))

        from agno.db.schemas.memory import UserMemory
        from agno.db.sqlite import SqliteDb
        from agno.run.agent import RunOutput, RunStatus
        from agno.session.agent import AgentSession

        self.SqliteDb = SqliteDb
        self.UserMemory = UserMemory
        self.AgentSession = AgentSession
        self.RunOutput = RunOutput
        self.RunStatus = RunStatus
        with closing(SqliteDb(db_file=str(self.caminho))) as banco:
            for protocolo, titular in (("original", ALVO), ("terceiro", OUTRO)):
                self.gravar_agno(banco, protocolo, titular)
        with self.conexao() as conexao:
            instalar_prototipo(conexao)
            conexao.executemany("INSERT INTO restricoes VALUES (?, 1, 'ativo')", [
                (chave(self.segredo, ALVO),), (chave(self.segredo, OUTRO),),
            ])
            conexao.executemany("INSERT INTO vinculos VALUES (?, ?)", [
                ("original", chave(self.segredo, ALVO)), ("diligencia", chave(self.segredo, ALVO)),
            ])

    @contextmanager
    def conexao(self, titular=None, geracao=None):
        with closing(conectar(self.caminho, self.segredo, titular, geracao)) as conexao, conexao:
            yield conexao

    @contextmanager
    def agno_configurado(self, titular, geracao):
        from sqlalchemy import create_engine
        from sqlalchemy.pool import NullPool

        engine = create_engine(
            "sqlite://", creator=lambda: conectar(self.caminho, self.segredo, titular, geracao),
            poolclass=NullPool, hide_parameters=True,
        )
        with closing(self.SqliteDb(db_engine=engine)) as banco:
            yield banco

    def gravar_agno(self, banco, protocolo, titular):
        self.assertIsNotNone(banco.upsert_session(self.AgentSession(session_id=protocolo, user_id=titular)))
        banco.upsert_run(self.RunOutput(
            run_id=protocolo, session_id=protocolo, user_id=titular,
            status=self.RunStatus.completed,
        ), session_id=protocolo, user_id=titular)
        self.assertIsNotNone(banco.get_run(protocolo))
        self.assertIsNotNone(banco.upsert_user_memory(self.UserMemory(
            memory_id=protocolo, user_id=titular, memory="marcador sintético",
        )))

    def admissao(self, titular):
        with self.conexao() as conexao:
            linha = conexao.execute(
                "SELECT geracao FROM restricoes WHERE chave = ? AND estado = 'ativo'",
                (chave(self.segredo, titular),),
            ).fetchone()
        return linha[0] if linha else None

    def bloquear(self):
        with self.conexao() as conexao:
            conexao.execute("BEGIN IMMEDIATE")
            conexao.execute("UPDATE restricoes SET estado = 'bloqueio_pendente' WHERE chave = ?",
                            (chave(self.segredo, ALVO),))

    def remover_fixture_bloqueada(self):
        # Simula a limpeza administrativa. O serviço real é exercitado no cenário J.
        with self.conexao() as conexao:
            dono = (ALVO,)
            conexao.execute("DELETE FROM agno_sessions WHERE user_id = ?", dono)
            conexao.execute("DELETE FROM agno_memories WHERE user_id = ?", dono)
            conexao.execute("UPDATE restricoes SET estado = 'excluido' WHERE chave = ?",
                            (chave(self.segredo, ALVO),))

    def contar(self, titular):
        with self.conexao() as conexao:
            return tuple(conexao.execute(f"SELECT count(*) FROM {tabela} WHERE user_id = ?",
                                         (titular,)).fetchone()[0] for tabela in TABELAS)

    def test_a_bloqueio_persiste_ao_reabrir(self):
        self.bloquear()
        self.assertIsNone(self.admissao(ALVO))
        with self.conexao(ALVO, 1) as nova:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "^barreira_persistente$"):
                gravar_sessao(nova, "a", ALVO)

    def test_b_escrita_tardia_apos_exclusao_simulada(self):
        geracao = self.admissao(ALVO)
        with self.conexao(ALVO, geracao) as execucao_antiga:
            self.bloquear()
            self.remover_fixture_bloqueada()
            with self.assertRaisesRegex(sqlite3.IntegrityError, "^barreira_persistente$"):
                gravar_sessao(execucao_antiga, "original", ALVO)
        self.assertEqual(self.contar(ALVO), (0, 0, 0))
        self.assertEqual(self.contar(OUTRO), (1, 1, 1))

    def test_c_admissao_e_escrita_depois_do_bloqueio(self):
        self.bloquear()
        trabalhos = []
        geracao = self.admissao(ALVO)
        if geracao is not None:
            trabalhos.append("iniciado")
        self.assertEqual(trabalhos, [])
        with self.conexao(ALVO, geracao) as conexao:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "^barreira_persistente$"):
                gravar_sessao(conexao, "c", ALVO)

    def test_d_diligencia_sem_titular_depende_de_vinculo_confiavel(self):
        with self.conexao(ALVO, 1) as conexao:
            gravar_sessao(conexao, "diligencia", None, '{"evento":"diligencia"}')
            with self.assertRaisesRegex(sqlite3.IntegrityError, "^barreira_persistente$"):
                gravar_sessao(conexao, "desconhecido", None, '{"texto":"' + ALVO + '"}')
        self.bloquear()
        with self.conexao(ALVO, 1) as conexao:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "^barreira_persistente$"):
                conexao.execute("UPDATE agno_sessions SET metadata = '{}' WHERE session_id = 'diligencia'")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "^barreira_persistente$"):
                conexao.execute("UPDATE agno_sessions SET user_id = ? WHERE session_id = 'diligencia'", (ALVO,))
            linha = conexao.execute("SELECT user_id FROM agno_sessions WHERE session_id = 'diligencia'").fetchone()
            self.assertEqual(linha, (None,))
        with self.conexao(OUTRO, 1) as conexao:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "^vinculo_incompativel$"):
                conexao.execute("UPDATE agno_sessions SET user_id = ? WHERE session_id = 'diligencia'", (OUTRO,))

    def test_e_outro_titular_continua_gravando_pelo_agno(self):
        self.bloquear()
        with self.agno_configurado(OUTRO, self.admissao(OUTRO)) as banco:
            self.gravar_agno(banco, "outro-e", OUTRO)
            self.gravar_agno(banco, "outro-e", OUTRO)  # Também exercita o UPSERT de registros existentes.
        with self.conexao(OUTRO, 1) as conexao:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "^vinculo_incompativel$"):
                conexao.execute("UPDATE agno_sessions SET user_id = ? WHERE session_id = 'original'", (OUTRO,))
        self.assertEqual(self.contar(OUTRO), (2, 2, 2))
        self.assertEqual(self.contar(ALVO), (1, 1, 1))

    def test_f_sqlitedb_direto_sem_funcoes_falha_fechado(self):
        from sqlalchemy.exc import OperationalError

        self.bloquear()
        with closing(self.SqliteDb(db_file=str(self.caminho))) as banco:
            banco.db_engine.hide_parameters = True
            with self.assertRaisesRegex(OperationalError, "no such function"):
                banco.upsert_session(self.AgentSession(session_id="direto", user_id=ALVO))
            with self.assertRaisesRegex(OperationalError, "no such function"):
                banco.upsert_run(self.RunOutput(run_id="direto", session_id="original", user_id=ALVO),
                                 session_id="original", user_id=ALVO)
            with self.assertRaisesRegex(OperationalError, "no such function"):
                banco.upsert_user_memory(self.UserMemory(memory_id="direto", memory="marcador", user_id=ALVO))
        self.assertEqual(self.contar(ALVO), (1, 1, 1))

    def test_g_memoria_tardia_recusada_no_upsert(self):
        from sqlalchemy.exc import IntegrityError

        geracao = self.admissao(ALVO)
        self.bloquear()
        with self.agno_configurado(ALVO, geracao) as banco:
            for ident in ("original", "nova-memoria"):
                with self.assertRaisesRegex(IntegrityError, "barreira_persistente"):
                    banco.upsert_user_memory(self.UserMemory(
                        memory_id=ident, memory="marcador tardio", user_id=ALVO,
                    ))
        self.assertEqual(self.contar(ALVO), (1, 1, 1))

    @contextmanager
    def processo(self, protocolo, manter_reserva):
        contexto = multiprocessing.get_context("spawn")
        leitor, filho = contexto.Pipe()
        processo = contexto.Process(
            target=escritor_independente, args=(self.caminho, self.segredo, protocolo, manter_reserva, filho),
        )
        processo.start()
        filho.close()
        try:
            yield leitor
            processo.join(15)
            self.assertEqual(processo.exitcode, 0)
        finally:
            leitor.close()
            if processo.is_alive():
                processo.terminate()
                processo.join(5)
            processo.close()

    def receber(self, canal):
        self.assertTrue(canal.poll(15), "Processo filho não respondeu.")
        return canal.recv()

    def test_h_duas_ordens_com_processos_independentes(self):
        with self.processo("antes", manter_reserva=True) as canal:
            self.assertEqual(self.receber(canal), "escrita_reservada")
            with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                self.bloquear()
            canal.send("confirmar")
            self.assertEqual(self.receber(canal), "gravado")
        self.assertEqual(self.contar(ALVO), (2, 1, 1))
        self.bloquear()
        with self.processo("depois", manter_reserva=False) as canal:
            self.assertEqual(self.receber(canal), "bloqueado")
        self.assertEqual(self.contar(ALVO), (2, 1, 1))
        print("H: escrita anterior confirmada; tentativa posterior recusada.", flush=True)

    def test_i_interrupcao_entre_bloqueio_pendente_e_exclusao(self):
        self.bloquear()
        # Simula a interrupção fechando a conexão sem executar a etapa de remoção.
        with self.conexao(ALVO, 1) as reaberta:
            estado = reaberta.execute("SELECT estado FROM restricoes WHERE chave = ?",
                                      (chave(self.segredo, ALVO),)).fetchone()[0]
            self.assertEqual(estado, "bloqueio_pendente")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "^barreira_persistente$"):
                gravar_sessao(reaberta, "i", ALVO)
        self.assertEqual(self.contar(ALVO), (1, 1, 1))

    def test_j_esquema_compatibilidade_e_limite_do_servico_atual(self):
        from barreira_persistente import BarreiraPersistente
        from exclusao_memoria import excluir_memoria_titular

        with self.agno_configurado(OUTRO, 1) as banco:
            self.gravar_agno(banco, "compatibilidade", OUTRO)
        with self.conexao() as conexao:
            total = conexao.execute("SELECT count(*) FROM sqlite_schema WHERE type = 'trigger'").fetchone()[0]
        self.assertEqual(total, 6)
        resultado = excluir_memoria_titular(
            ALVO, caminho_banco=self.caminho, banco_autorizado=self.caminho,
            barreira=BarreiraPersistente(self.segredo),
        )
        self.assertEqual(resultado["status"], "bloqueado")
        self.assertEqual(resultado["conflitos"], {"esquema_nao_suportado": 1})
        self.assertEqual(self.contar(ALVO), (1, 1, 1))

    def test_k_geracao_anterior_nao_grava_apos_reativacao_simulada(self):
        from sqlalchemy.exc import IntegrityError

        anterior = self.admissao(ALVO)
        self.bloquear()
        self.remover_fixture_bloqueada()
        with self.conexao() as conexao:
            conexao.execute("UPDATE restricoes SET estado = 'ativo', geracao = geracao + 1 WHERE chave = ?",
                            (chave(self.segredo, ALVO),))
        nova = self.admissao(ALVO)
        self.assertEqual(nova, anterior + 1)
        with self.agno_configurado(ALVO, nova) as banco:
            self.gravar_agno(banco, "reativado", ALVO)
        with self.agno_configurado(ALVO, anterior) as banco:
            for acao in (
                lambda: banco.upsert_session(self.AgentSession(session_id="atrasado", user_id=ALVO)),
                lambda: banco.upsert_run(self.RunOutput(run_id="atrasado", session_id="reativado", user_id=ALVO),
                                        session_id="reativado", user_id=ALVO),
                lambda: banco.upsert_user_memory(self.UserMemory(memory_id="reativado", memory="antiga", user_id=ALVO)),
            ):
                with self.assertRaisesRegex(IntegrityError, "barreira_persistente"):
                    acao()
        self.assertEqual(self.contar(ALVO), (1, 1, 1))

    def test_l_restricoes_guardam_hmac_e_nao_matricula(self):
        self.bloquear()
        with self.conexao() as conexao:
            tokens = {linha[0] for linha in conexao.execute("SELECT chave FROM restricoes")}
        self.assertTrue(tokens == {chave(self.segredo, ALVO), chave(self.segredo, OUTRO)})
        for titular in (ALVO, OUTRO):
            self.assertFalse(titular.encode("ascii") in tokens)
            self.assertFalse(hashlib.sha256(titular.encode("ascii")).digest() in tokens)
        self.assertTrue(all(isinstance(token, bytes) and len(token) == 32 for token in tokens))

    def preparar_producao(self):
        from barreira_persistente import BarreiraPersistente

        caminho = self.caminho.with_name("producao-temporaria.db")
        caminhos = {"caminho_banco": caminho, "banco_autorizado": caminho}
        with closing(self.SqliteDb(db_file=str(caminho))) as banco:
            self.gravar_agno(banco, "protegido", ALVO)
            self.gravar_agno(banco, "outro", OUTRO)
        barreira = BarreiraPersistente(self.segredo)
        barreira.preparar(**caminhos)
        return barreira, caminhos

    def test_producao_exclusao_impede_memoria_run_e_diligencia_tardios(self):
        from barreira_persistente import BarreiraPersistente
        from exclusao_memoria import excluir_memoria_titular
        from sqlalchemy.exc import IntegrityError, OperationalError

        barreira, caminhos = self.preparar_producao()
        with barreira.abrir_agno(ALVO, **caminhos) as antigo:
            resultado = excluir_memoria_titular(ALVO, barreira=barreira, **caminhos)
            self.assertEqual(resultado["status"], "excluido", resultado)
            for gravar in (
                lambda: antigo.upsert_session(self.AgentSession(session_id="protegido", user_id=ALVO)),
                lambda: antigo.upsert_run(self.RunOutput(run_id="atrasado", session_id="protegido", user_id=ALVO),
                                         session_id="protegido", user_id=ALVO),
                lambda: antigo.upsert_user_memory(self.UserMemory(memory_id="nova", memory="atrasada", user_id=ALVO)),
                lambda: antigo.upsert_session(self.AgentSession(session_id="protegido", user_id=None)),
            ):
                with self.assertRaisesRegex(IntegrityError, "barreira_"):
                    gravar()
        with closing(self.SqliteDb(db_file=str(caminhos["caminho_banco"]))) as direto:
            direto.db_engine.hide_parameters = True
            with self.assertRaisesRegex(OperationalError, "no such function"):
                direto.upsert_session(self.AgentSession(session_id="direto", user_id=ALVO))
            self.assertIsNone(direto.get_session("protegido"))
        reiniciada = BarreiraPersistente(self.segredo)
        with self.assertRaisesRegex(PermissionError, "barreira_bloqueada"), reiniciada.abrir_agno(ALVO, **caminhos):
            self.fail("Admissão concedida ao titular bloqueado.")
        errada = BarreiraPersistente(secrets.token_bytes(32))
        with self.assertRaisesRegex(ValueError, "chave_da_barreira_incompativel"), errada.abrir_agno(OUTRO, **caminhos):
            self.fail("Admissão concedida com chave incompatível.")
        with reiniciada.abrir_agno(OUTRO, **caminhos) as banco:
            self.assertIsNotNone(banco.get_session("outro", user_id=OUTRO))
            self.gravar_agno(banco, "novo-do-outro", OUTRO)
            with self.assertRaisesRegex(IntegrityError, "barreira_vinculo"):
                banco.upsert_session(self.AgentSession(session_id="protegido", user_id=OUTRO))

    def test_producao_preserva_bloqueio_apos_falha_e_outro_processo(self):
        from exclusao_memoria import excluir_memoria_titular

        barreira, caminhos = self.preparar_producao()
        with patch("exclusao_memoria._excluir", side_effect=RuntimeError("falha antes de excluir")):
            resultado = excluir_memoria_titular(ALVO, barreira=barreira, **caminhos)
        self.assertNotEqual(resultado["status"], "excluido")
        caminho = caminhos["caminho_banco"]
        with closing(sqlite3.connect(caminho)) as conexao:
            self.assertEqual(conexao.execute("SELECT estado FROM barreira_restricoes").fetchone(),
                             ("bloqueio_pendente",))
        contexto = multiprocessing.get_context("spawn")
        receptor, emissor = contexto.Pipe(duplex=False)
        processo = contexto.Process(target=escritor_producao, args=(caminho, self.segredo, emissor))
        processo.start()
        emissor.close()
        try:
            self.assertTrue(receptor.poll(30))
            self.assertTrue(receptor.recv())
            processo.join(15)
            self.assertEqual(processo.exitcode, 0)
        finally:
            receptor.close()
            if processo.is_alive():
                processo.terminate()
                processo.join(5)
            processo.close()
        self.assertEqual(excluir_memoria_titular(ALVO, barreira=barreira, **caminhos)["status"], "excluido")
        with closing(sqlite3.connect(caminho)) as conexao:
            # A matrícula sintética deste cenário não possui nome cadastral.
            self.assertEqual(conexao.execute("SELECT estado FROM barreira_restricoes").fetchone(), ("revisao_manual",))
            self.assertEqual(conexao.execute("SELECT count(*) FROM agno_sessions").fetchone(), (1,))

    def test_producao_diligencias_e_retomadas_admitem_apenas_titular_ativo(self):
        from agno.models.response import ModelResponse
        from complementacoes import aplicar_complementacao
        from execucao_interativa import executar_tentativa
        from exclusao_memoria import excluir_memoria_titular
        from persistencia_sessoes import registrar_complementacao, registrar_diligencia
        from sqlalchemy.exc import IntegrityError

        with patch("dotenv.load_dotenv", return_value=False):
            import agente

        barreira, caminhos = self.preparar_producao()
        caminho = caminhos["caminho_banco"]
        chamadas = []

        class ModeloOffline(agente.OpenAIResponses):
            def invoke(self, messages, **kwargs):
                chamadas.append(kwargs["run_response"].session_id)
                return ModelResponse()

        with patch.object(agente, "OpenAIResponses", ModeloOffline):
            for protocolo in ("DIA-2026-0111", "DIA-2026-0112"):
                pedido = aplicar_complementacao(protocolo)["pedido_corrigido"]
                titular = pedido["matricula"]
                barreira.vincular_protocolo_validado(protocolo, titular, **caminhos)
                with barreira.abrir_agno(titular, **caminhos) as banco:
                    preliminar = registrar_diligencia(protocolo, caminho_banco=caminho, banco_protegido=banco)
                    self.assertIsNone(preliminar.user_id)
                    corrigida = registrar_complementacao(protocolo, caminho_banco=caminho, banco_protegido=banco)
                    self.assertTrue(corrigida.user_id == titular)
                parametros = dict(
                    protocolo=protocolo, session_id=protocolo, pedido=pedido, user_id=titular, usar_memoria=True,
                    barreira_persistente=barreira, **caminhos,
                )
                sem_protecao = parametros | {"barreira_persistente": None}
                resultado = executar_tentativa(tentativa_id=str(uuid4()), **sem_protecao)
                self.assertEqual(resultado["status"], "analise_manual")
                tentativa = str(uuid4())
                executar_tentativa(tentativa_id=tentativa, **parametros)
                with barreira.abrir_agno(titular, **caminhos) as antigo:
                    self.assertIsNotNone(antigo.get_run(tentativa))
                    resultado = excluir_memoria_titular(titular, barreira=barreira, **caminhos)
                    self.assertEqual(resultado["status"], "excluido", resultado["conflitos"])
                    self.assertTrue(resultado["bloqueio_confirmado"])
                    with self.assertRaises(RuntimeError):
                        registrar_diligencia(protocolo, caminho_banco=caminho, banco_protegido=antigo)
                resultado = executar_tentativa(tentativa_id=str(uuid4()), **parametros)
                self.assertEqual(resultado["status"], "analise_manual")
                with barreira.abrir_agno(OUTRO, **caminhos) as outro:
                    with self.assertRaisesRegex(IntegrityError, "barreira_vinculo"):
                        outro.upsert_session(self.AgentSession(session_id=protocolo, user_id=OUTRO))
        self.assertEqual(chamadas, ["DIA-2026-0111", "DIA-2026-0112"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
