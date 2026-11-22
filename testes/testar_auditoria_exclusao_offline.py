"""Auditoria da exclusão lógica, com SQLite descartável e leitura independente."""

import hashlib
import json
import secrets
import socket
import sqlite3
import sys
import tempfile
import unittest
from contextlib import ExitStack, closing
from importlib.metadata import version
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ALVO = "990071"
OUTRO = "990084"
NOME = "Pessoa Ficticia Auditoria Zeta"
CPF_FICTICIO = "000.000.000-00"
BANCO_FICTICIO = "agência 0000 conta 000000-0"
TABELAS = ("agno_sessions", "agno_runs", "agno_memories")
ZERO = {"sessoes": 0, "execucoes": 0, "memorias": 0}


def contem(valor, marcador):
    if isinstance(valor, dict):
        return any(contem(item, marcador) for par in valor.items() for item in par)
    if isinstance(valor, list):
        return any(contem(item, marcador) for item in valor)
    if isinstance(valor, str):
        if marcador in valor:
            return True
        if valor.lstrip().startswith(("{", "[", '"')):
            try:
                decodificado = json.loads(valor)
            except ValueError:
                return False
            return contem(decodificado, marcador)
    return False


class AuditoriaExclusaoOffline(unittest.TestCase):
    def setUp(self):
        self.assertEqual(version("agno"), "3.2.1")
        recursos = self.enterContext(ExitStack())
        pasta = recursos.enter_context(tempfile.TemporaryDirectory())
        self.caminho = Path(pasta).resolve() / "auditoria.db"
        bloqueios = []

        def negar(*args, **kwargs):
            bloqueios.append(True)
            raise AssertionError("Acesso externo bloqueado.")

        recursos.callback(lambda: self.assertFalse(bloqueios, "Houve tentativa de acesso externo."))
        for nome in ("connect", "connect_ex", "send", "sendall", "sendto"):
            recursos.enter_context(patch.object(socket.socket, nome, negar))
        for nome in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
            recursos.enter_context(patch.object(socket, nome, negar))
        for nome in ("openai.OpenAI.__init__", "openai.AsyncOpenAI.__init__"):
            recursos.enter_context(patch(nome, negar))
        recursos.enter_context(patch("dotenv.load_dotenv", return_value=False))

        from agno.db.sqlite import SqliteDb
        from barreira_persistente import BarreiraPersistente
        from exclusao_memoria import excluir_memoria_titular

        self.excluir = excluir_memoria_titular
        self.barreira = BarreiraPersistente(secrets.token_bytes(32))
        self.banco = SqliteDb(db_file=str(self.caminho))
        recursos.callback(self.banco.close)

    def preparar(self, identificador, titular, texto):
        from agno.db.schemas.memory import UserMemory
        from agno.models.message import Message
        from agno.run.agent import RunOutput, RunStatus
        from agno.session.agent import AgentSession

        self.assertIsNotNone(self.banco.upsert_session(AgentSession(
            session_id=identificador, user_id=titular, metadata={"documento": {"texto": texto}},
        )))
        self.banco.upsert_run(RunOutput(
            run_id=identificador, session_id=identificador, user_id=titular,
            status=RunStatus.completed, messages=[Message(role="user", content=texto)],
        ), session_id=identificador, user_id=titular)
        self.assertIsNotNone(self.banco.get_run(identificador))
        self.assertIsNotNone(self.banco.upsert_user_memory(UserMemory(
            memory_id=identificador, user_id=titular, memory=texto, input=texto,
        )))

    def executar(self):
        return self.excluir(
            ALVO, caminho_banco=self.caminho, banco_autorizado=self.caminho, barreira=self.barreira,
        )

    def ler(self):
        with closing(sqlite3.connect(self.caminho.as_uri() + "?mode=ro", uri=True)) as conexao:
            conexao.row_factory = sqlite3.Row
            consulta = "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            tabelas = [linha[0] for linha in conexao.execute(consulta)]
            return {
                tabela: [dict(linha) for linha in conexao.execute(
                    'SELECT * FROM "' + tabela.replace('"', '""') + '"'
                )]
                for tabela in tabelas if tabela not in {
                    "barreira_config", "barreira_protocolos", "barreira_restricoes",
                }
            }

    def hashes(self, dados, titular=None):
        ids = dict(zip(TABELAS, ("session_id", "run_id", "memory_id")))
        return {
            tabela: {
                linha[ids[tabela]]: hashlib.sha256(json.dumps(linha, sort_keys=True).encode()).hexdigest()
                for linha in dados[tabela] if titular is None or linha["user_id"] == titular
            }
            for tabela in TABELAS
        }

    def residuos(self, dados, *marcadores):
        return {
            tabela: sum(any(contem(linha, marcador) for marcador in marcadores) for linha in linhas)
            for tabela, linhas in dados.items()
        }

    def preservar(self, antes):
        depois = self.ler()
        self.assertTrue(antes == depois, "A exclusão bloqueada alterou linhas do SQLite.")

    def test_a_exclusao_logica_completa(self):
        self.preparar("a", ALVO, ALVO)
        antes = self.ler()
        self.assertTrue(set(TABELAS).issubset(antes))
        self.assertEqual(sum(self.residuos(antes, ALVO).values()), 3)
        relatorio = self.executar()
        self.assertEqual(relatorio["status"], "excluido")
        self.assertEqual(relatorio["depois"], ZERO)
        depois = self.ler()
        self.assertTrue(all(not depois[tabela] for tabela in TABELAS))
        contagens = self.residuos(depois, ALVO)
        self.assertEqual(contagens, dict.fromkeys(antes, 0))
        print(json.dumps({"A": contagens}), flush=True)

    def test_b_ids_e_hashes_de_terceiros_preservados(self):
        self.preparar("a", ALVO, ALVO)
        self.preparar("b", OUTRO, "marcador de terceiro")
        antes = self.hashes(self.ler(), OUTRO)
        self.assertEqual(sum(map(len, antes.values())), 3)
        self.assertEqual(self.executar()["status"], "excluido")
        depois = self.hashes(self.ler(), OUTRO)
        self.assertTrue(antes == depois, "IDs ou hashes do outro titular mudaram.")

    def test_c_matricula_detectada_em_json_input_e_legado(self):
        self.preparar("a", ALVO, "registros do alvo")
        self.preparar("b", OUTRO, ALVO)
        with closing(sqlite3.connect(self.caminho)) as conexao, conexao:
            conexao.execute("ALTER TABLE agno_sessions ADD COLUMN runs JSON")
            conexao.execute("UPDATE agno_sessions SET runs = ? WHERE session_id = ?",
                            (json.dumps([{"mensagem": ALVO}]), "b"))
        antes = self.ler()
        terceiro = next(linha for linha in antes["agno_sessions"] if linha["session_id"] == "b")
        self.assertTrue(all(contem(terceiro[campo], ALVO) for campo in ("metadata", "runs")))
        run = next(linha for linha in antes["agno_runs"] if linha["run_id"] == "b")
        self.assertTrue(contem(run["run_data"], ALVO))
        memoria = next(linha for linha in antes["agno_memories"] if linha["memory_id"] == "b")
        self.assertTrue(all(contem(memoria[campo], ALVO) for campo in ("memory", "input")))
        relatorio = self.executar()
        self.assertEqual(relatorio["status"], "bloqueado")
        self.assertEqual(relatorio["conflitos"]["historico_legado_nao_resolvido"], 1)
        contagens = self.residuos(antes, ALVO)
        self.assertEqual(relatorio["residuos"], {t: n for t, n in contagens.items() if n})
        self.preservar(antes)
        print(json.dumps({"C": contagens}), flush=True)

    def test_d_diligencia_sem_titular_nao_vira_propriedade(self):
        from agno.session.agent import AgentSession

        self.preparar("a", ALVO, "registros do alvo")
        self.banco.upsert_session(AgentSession(
            session_id="diligencia", user_id=None,
            metadata={"eventos_administrativos": [{"tipo": "diligencia_preliminar", "texto": ALVO}]},
        ))
        antes = self.ler()
        relatorio = self.executar()
        self.assertEqual(relatorio["antes"], {"sessoes": 1, "execucoes": 1, "memorias": 1})
        self.assertEqual(relatorio["status"], "bloqueado")
        self.assertEqual(relatorio["conflitos"]["sessao_sem_titular"], 1)
        self.assertTrue(relatorio["revisao_manual"])
        self.preservar(antes)

    def test_e_cascata_cruzada_e_bloqueada_antes_de_excluir(self):
        from agno.run.agent import RunOutput

        self.preparar("a", ALVO, "registros do alvo")
        self.preparar("b", OUTRO, "registros de terceiro")
        self.banco.upsert_run(RunOutput(run_id="divergente", session_id="a", user_id=OUTRO),
                              session_id="a", user_id=OUTRO)
        antes = self.ler()
        with patch.object(type(self.banco), "delete_session") as excluir_sessao, patch.object(
            type(self.banco), "delete_user_memories",
        ) as excluir_memorias:
            relatorio = self.executar()
            excluir_sessao.assert_not_called()
            excluir_memorias.assert_not_called()
        self.assertEqual(relatorio["status"], "bloqueado")
        self.assertEqual(relatorio["conflitos"]["titular_da_execucao_incompativel"], 1)
        self.preservar(antes)

    def test_f_orfao_permanece_e_impede_exclusao_completa(self):
        self.preparar("a", ALVO, "registros do alvo")
        with closing(sqlite3.connect(self.caminho)) as conexao, conexao:
            conexao.execute("PRAGMA foreign_keys = OFF")
            linha = conexao.execute("SELECT run_data FROM agno_runs WHERE run_id = 'a'").fetchone()
            dados = json.loads(linha[0])
            dados["session_id"] = "ausente"
            conexao.execute("UPDATE agno_runs SET session_id = ?, run_data = ? WHERE run_id = 'a'",
                            ("ausente", json.dumps(dados)))
        antes = self.ler()
        relatorio = self.executar()
        self.assertEqual(relatorio["status"], "bloqueado")
        self.assertEqual(relatorio["conflitos"]["execucao_orfa"], 1)
        self.assertTrue(relatorio["revisao_manual"])
        self.preservar(antes)

    def test_g_falha_reverte_tudo_e_repeticao_confirma_ausencia(self):
        self.preparar("a", ALVO, "registros do alvo")
        self.preparar("b", OUTRO, "registros de terceiro")
        antes = self.ler()

        def falhar(banco, ids, *, user_id):
            self.assertIsNone(banco.get_session("a", user_id=user_id))
            raise RuntimeError("Falha sintética depois da etapa de sessões.")

        with patch.object(type(self.banco), "delete_user_memories", falhar):
            falha = self.executar()
        self.assertEqual(falha["status"], "erro")
        self.assertEqual(falha["conflitos"]["exclusao_revertida"], 1)
        self.preservar(antes)
        self.assertEqual(self.executar()["status"], "excluido")
        removidos = self.ler()
        nova = self.executar()
        self.assertEqual(nova["status"], "sem_registros")
        self.assertEqual(nova["antes"], ZERO)
        self.assertEqual(nova["depois"], ZERO)
        self.preservar(removidos)

    def test_h_reserva_e_barreira_recusam_escrita_posterior(self):
        from agno.session.agent import AgentSession
        from sqlalchemy.exc import IntegrityError

        self.preparar("a", ALVO, "registros do alvo")
        caminhos = {"caminho_banco": self.caminho, "banco_autorizado": self.caminho}
        self.barreira.preparar(**caminhos)
        antes = self.ler()
        with closing(sqlite3.connect(self.caminho, timeout=0)) as escritor:
            escritor.execute("BEGIN IMMEDIATE")
            bloqueio = self.executar()
            self.assertEqual(bloqueio["status"], "bloqueado")
            self.assertEqual(bloqueio["conflitos"]["escrita_concorrente"], 1)
            escritor.rollback()
        self.preservar(antes)
        with self.barreira.abrir_agno(ALVO, **caminhos) as agente_antigo:
            self.assertEqual(self.executar()["status"], "excluido")
            with self.assertRaisesRegex(IntegrityError, "barreira_bloqueada"):
                agente_antigo.upsert_session(AgentSession(session_id="posterior", user_id=ALVO))
        with self.assertRaises(PermissionError):
            with self.barreira.abrir_agno(ALVO, **caminhos):
                self.fail("O titular bloqueado foi admitido.")
        contagens = self.residuos(self.ler(), ALVO)
        self.assertEqual(sum(contagens.values()), 0)
        print(json.dumps({"H": {"residuos_apos_tentativa_tardia": contagens}}), flush=True)

    def test_i_matricula_codificada_detectada_com_terceiro_preservado(self):
        texto = f"{NOME} | CPF {CPF_FICTICIO} | {BANCO_FICTICIO}"
        self.preparar("a", ALVO, texto)
        self.preparar("b", OUTRO, texto)
        escape = "".join(f"\\u{ord(digito):04x}" for digito in ALVO)
        with closing(sqlite3.connect(self.caminho)) as conexao, conexao:
            conexao.execute("UPDATE agno_sessions SET metadata = ? WHERE session_id = 'b'",
                            ('{"matricula_referenciada":"' + escape + '","texto":' + json.dumps(texto) + '}',))
        antes = self.ler()
        preservados = self.hashes(antes, OUTRO)
        relatorio = self.executar()
        self.assertEqual(relatorio["status"], "excluido")
        self.assertEqual(relatorio["depois"], ZERO)
        self.assertEqual(relatorio["residuos"], {"agno_sessions": 1})
        self.assertTrue(relatorio["revisao_manual"])
        depois = self.ler()
        self.assertTrue(preservados == self.hashes(depois, OUTRO))
        contagens = self.residuos(depois, NOME, CPF_FICTICIO, BANCO_FICTICIO)
        matricula_json = self.residuos(depois, ALVO)
        self.assertEqual(sum(contagens.values()), 3)
        self.assertEqual(matricula_json["agno_sessions"], 1)
        self.assertEqual(sum(matricula_json.values()), 1)
        self.assertTrue(all(valor not in json.dumps(relatorio) for valor in (ALVO, NOME, CPF_FICTICIO, BANCO_FICTICIO)))
        print(json.dumps({"I": {"marcadores_pessoais": contagens, "matricula_em_json": matricula_json,
                                "relatorio_detectou": bool(relatorio["residuos"])}}), flush=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
