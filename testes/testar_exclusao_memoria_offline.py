"""Experimentos com a API SQLite do Agno, em bancos descartáveis e sem modelo."""

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

ALFA = "titular-sintetico-alfa"
BETA = "titular-sintetico-beta"
SESSAO_A = "sessao-sintetica-alfa"
SESSAO_B = "sessao-sintetica-beta"
MARCADOR_A = "MARCADOR_SINTETICO_ALFA"
MARCADOR_B = "MARCADOR_SINTETICO_BETA"
RUN_DIVERGENTE = "run-sintetico-divergente"
VALIDA_A = "900001"
VALIDA_B = "900002"


class ExclusaoMemoriaOffline(unittest.TestCase):
    def setUp(self):
        self.assertEqual(version("agno"), "3.2.1")
        recursos = self.enterContext(ExitStack())
        self.caminho = Path(recursos.enter_context(tempfile.TemporaryDirectory())) / "experimento.db"
        acessos_bloqueados = []

        def bloquear(*args, **kwargs):
            acessos_bloqueados.append(True)
            raise AssertionError("Acesso externo bloqueado.")

        recursos.callback(lambda: self.assertFalse(acessos_bloqueados, "Houve tentativa de rede."))
        for nome in ("connect", "connect_ex", "sendto", "send", "sendall"):
            recursos.enter_context(patch.object(socket.socket, nome, bloquear))
        for nome in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
            recursos.enter_context(patch.object(socket, nome, bloquear))
        for nome in ("openai.OpenAI.__init__", "openai.AsyncOpenAI.__init__"):
            recursos.enter_context(patch(nome, bloquear))

        from agno.db.sqlite import SqliteDb

        self.banco = SqliteDb(db_file=str(self.caminho))
        recursos.callback(self.banco.close)

    def criar_sessao(self, sessao, titular, marcador):
        from agno.session.agent import AgentSession

        criada = self.banco.upsert_session(AgentSession(
            session_id=sessao, agent_id="agente-sintetico", user_id=titular,
            metadata={"marcador": marcador},
        ))
        self.assertIsNotNone(criada)

    def criar_run(self, sessao, titular, marcador, run_id):
        from agno.models.message import Message
        from agno.run.agent import RunOutput, RunStatus

        run = RunOutput(
            run_id=run_id, session_id=sessao, user_id=titular, agent_id="agente-sintetico",
            status=RunStatus.completed, messages=[Message(role="user", content=marcador)],
        )
        self.banco.upsert_run(run, session_id=sessao, user_id=titular)
        self.assertIsNotNone(self.banco.get_run(run_id))
        return run

    def criar_par(self):
        from agno.db.schemas.memory import UserMemory

        for sessao, titular, marcador in ((SESSAO_A, ALFA, MARCADOR_A), (SESSAO_B, BETA, MARCADOR_B)):
            self.criar_sessao(sessao, titular, marcador)
            self.criar_run(sessao, titular, marcador, f"run-{sessao}")
            memoria = UserMemory(memory=marcador, input=marcador, user_id=titular)
            self.assertIsNotNone(self.banco.upsert_user_memory(memoria))

    def inventario(self, titular):
        sessoes, _ = self.banco.get_sessions(user_id=titular, deserialize=False, include_runs=False)
        runs, _ = self.banco.get_runs(user_id=titular, deserialize=False)
        memorias, _ = self.banco.get_user_memories(user_id=titular, deserialize=False)
        return sessoes, runs, memorias

    def conferir_vinculos(self, sessao, titular):
        atual = self.banco.get_session(sessao, deserialize=False)
        self.assertIsNotNone(atual)
        self.assertEqual(atual["user_id"], titular)
        runs, _ = self.banco.get_runs(session_id=sessao, deserialize=False)
        self.assertEqual(len(runs), 1)
        self.assertTrue(all(run["user_id"] == titular for run in runs))
        self.assertTrue(all(run["user_id"] == titular for run in atual.get("runs") or []))

    def contar_residuos(self, marcador):
        # Leitura lógica em conexão nova, inclusive texto JSON serializado.
        with closing(sqlite3.connect(self.caminho.as_uri() + "?mode=ro", uri=True)) as conexao:
            tabelas = conexao.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            contagens = {}
            for (tabela,) in sorted(tabelas):
                identificador = '"' + tabela.replace('"', '""') + '"'
                linhas = conexao.execute(f"SELECT * FROM {identificador}")
                contagens[tabela] = sum(
                    any(isinstance(valor, str) and marcador in valor for valor in linha)
                    for linha in linhas
                )
        return contagens

    def test_a_exclusao_normal_preserva_outro_titular(self):
        self.criar_par()
        outro_antes = self.inventario(BETA)
        self.assertEqual(tuple(map(len, outro_antes)), (1, 1, 1))
        self.conferir_vinculos(SESSAO_A, ALFA)
        self.assertTrue(self.banco.delete_session(SESSAO_A, user_id=ALFA))
        self.assertEqual(tuple(map(len, self.inventario(ALFA))), (0, 0, 1))
        memorias = self.banco.get_user_memories(user_id=ALFA)
        self.banco.delete_user_memories([memoria.memory_id for memoria in memorias], user_id=ALFA)
        self.assertEqual(tuple(map(len, self.inventario(ALFA))), (0, 0, 0))
        self.assertTrue(self.inventario(BETA) == outro_antes, "Inventário do outro titular mudou.")

    def test_b_memorias_excluidas_com_filtro_de_titular(self):
        self.criar_par()
        memorias_a = self.banco.get_user_memories(user_id=ALFA)
        memorias_b = self.banco.get_user_memories(user_id=BETA)
        self.assertEqual((len(memorias_a), len(memorias_b)), (1, 1))
        ids = [memorias_a[0].memory_id, memorias_b[0].memory_id]
        self.banco.delete_user_memories(ids, user_id=ALFA)
        self.assertFalse(self.banco.get_user_memories(user_id=ALFA))
        restantes = self.banco.get_user_memories(user_id=BETA)
        self.assertTrue(restantes == memorias_b, "A memória do outro titular mudou.")
        self.assertEqual(tuple(map(len, self.inventario(ALFA))), (1, 1, 0))

    def test_c_experimento_observa_perda_cruzada_por_cascata(self):
        from sqlalchemy import event

        self.criar_sessao(SESSAO_A, ALFA, MARCADOR_A)
        self.criar_run(SESSAO_A, BETA, MARCADOR_B, RUN_DIVERGENTE)
        sessao = self.banco.get_session(SESSAO_A)
        runs, _ = self.banco.get_runs(session_id=SESSAO_A, deserialize=False)
        self.assertEqual(sessao.user_id, ALFA)
        self.assertEqual([run["user_id"] for run in runs], [BETA])
        with self.banco.db_engine.connect() as conexao:
            self.assertEqual(conexao.exec_driver_sql("PRAGMA foreign_keys").scalar_one(), 1)
            fks = conexao.exec_driver_sql("PRAGMA foreign_key_list(agno_runs)").mappings().all()
        self.assertTrue(any(
            fk["table"] == "agno_sessions" and fk["from"] == "session_id" and fk["on_delete"] == "CASCADE"
            for fk in fks
        ))
        self.assertFalse(self.banco.delete_session(SESSAO_A, user_id=BETA))
        self.assertIsNotNone(self.banco.get_run(RUN_DIVERGENTE))

        presentes_antes_delete_explicito = []

        def observar_delete(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("DELETE FROM AGNO_RUNS "):
                with closing(cursor.connection.cursor()) as leitura:
                    leitura.execute("SELECT COUNT(*) FROM agno_runs WHERE run_id = ?", (RUN_DIVERGENTE,))
                    presentes_antes_delete_explicito.append(leitura.fetchone()[0])

        event.listen(self.banco.db_engine, "before_cursor_execute", observar_delete)
        try:
            # Experimento destrutivo deliberado, sobre o banco descartável deste cenário.
            self.assertTrue(self.banco.delete_session(SESSAO_A, user_id=ALFA))
        finally:
            event.remove(self.banco.db_engine, "before_cursor_execute", observar_delete)
        self.assertEqual(presentes_antes_delete_explicito, [0])
        perda_cruzada = self.banco.get_run(RUN_DIVERGENTE) is None
        self.assertTrue(perda_cruzada, "O comportamento destrutivo esperado mudou.")
        print(json.dumps({"C": {"agno_runs": 0, "perda_cruzada_observada": perda_cruzada,
                                "isolamento_preservado": not perda_cruzada}}), flush=True)

    def test_d_diligencia_sem_titular_nao_aparece_no_filtro(self):
        self.criar_sessao(SESSAO_A, None, MARCADOR_A)
        self.assertFalse(self.banco.get_sessions(user_id=ALFA))
        self.assertFalse(self.banco.get_sessions(user_id=BETA))
        self.assertIsNone(self.banco.get_session(SESSAO_A, user_id=ALFA))
        sem_titular = self.banco.get_session(SESSAO_A)
        self.assertIsNotNone(sem_titular)
        self.assertIsNone(sem_titular.user_id)
        self.assertEqual(self.contar_residuos(MARCADOR_A), {"agno_schema_versions": 0, "agno_sessions": 1})

    def test_e_localiza_run_legado_e_orfao(self):
        from agno.db.sqlite import SqliteDb

        self.criar_sessao(SESSAO_B, BETA, MARCADOR_B)
        legado = self.criar_run(SESSAO_B, ALFA, MARCADOR_A, "run-legado")
        orfao = self.criar_run(SESSAO_B, None, MARCADOR_A, "run-orfao")
        orfao.session_id = "sessao-inexistente"

        # Simula uma migração incompleta e um escritor antigo sem FK ativa.
        # As alterações atingem apenas o arquivo temporário desta instância.
        with closing(sqlite3.connect(self.caminho)) as conexao, conexao:
            conexao.execute("PRAGMA foreign_keys = OFF")
            conexao.execute("ALTER TABLE agno_sessions ADD COLUMN runs JSON")
            conexao.execute("UPDATE agno_sessions SET runs = ? WHERE session_id = ?",
                            (json.dumps([legado.to_dict()]), SESSAO_B))
            conexao.execute("DELETE FROM agno_runs WHERE run_id = ?", (legado.run_id,))
            conexao.execute("UPDATE agno_runs SET session_id = ?, run_data = ? WHERE run_id = ?",
                            (orfao.session_id, json.dumps(orfao.to_dict()), orfao.run_id))

        # Um adaptador novo reflete o esquema preexistente, inclusive a coluna legada.
        banco_legado = SqliteDb(db_file=str(self.caminho))
        with closing(banco_legado):
            self.assertFalse(banco_legado.get_sessions(user_id=ALFA, include_runs=False))
            self.assertFalse(banco_legado.get_runs(user_id=ALFA))
            recuperada = banco_legado.get_session(SESSAO_B)
        self.assertEqual(len(recuperada.runs), 1)
        self.assertTrue(recuperada.runs[0].user_id == ALFA)
        with closing(sqlite3.connect(self.caminho.as_uri() + "?mode=ro", uri=True)) as conexao:
            orfaos = conexao.execute(
                "SELECT COUNT(*) FROM agno_runs r LEFT JOIN agno_sessions s ON r.session_id = s.session_id "
                "WHERE s.session_id IS NULL"
            ).fetchone()[0]
            violacoes = conexao.execute("PRAGMA foreign_key_check").fetchall()
        self.assertEqual(orfaos, 1)
        self.assertEqual(len(violacoes), 1)
        residuos = self.contar_residuos(MARCADOR_A)
        self.assertEqual(residuos, {"agno_runs": 1, "agno_schema_versions": 0, "agno_sessions": 1})
        print(json.dumps({"E": {"residuos": residuos, "orfaos": orfaos}}), flush=True)

    def test_f_repeticao_distingue_ausencia_de_erro(self):
        self.criar_par()
        self.conferir_vinculos(SESSAO_A, ALFA)
        ids = [memoria.memory_id for memoria in self.banco.get_user_memories(user_id=ALFA)]
        self.assertEqual(len(ids), 1)
        primeira = self.banco.delete_session(SESSAO_A, user_id=ALFA)
        primeira_memoria = self.banco.delete_user_memories(ids, user_id=ALFA)
        segunda = self.banco.delete_session(SESSAO_A, user_id=ALFA)
        segunda_memoria = self.banco.delete_user_memories(ids, user_id=ALFA)
        self.assertEqual((primeira, segunda), (True, False))
        self.assertIsNone(primeira_memoria)
        self.assertIsNone(segunda_memoria)
        self.assertEqual(tuple(map(len, self.inventario(ALFA))), (0, 0, 0))
        self.assertEqual(tuple(map(len, self.inventario(BETA))), (1, 1, 1))
        print(json.dumps({"F": {"primeira_excluiu_sessao": primeira, "segunda_excluiu_sessao": segunda,
                                "retorno_memorias_sem_status": segunda_memoria is None}}), flush=True)

    def test_g_confere_residuos_sem_expor_conteudo(self):
        self.criar_par()
        esperado = {"agno_memories": 1, "agno_runs": 1, "agno_schema_versions": 0, "agno_sessions": 1}
        self.assertEqual(self.contar_residuos(MARCADOR_A), esperado)
        self.assertEqual(self.contar_residuos(MARCADOR_B), esperado)
        self.conferir_vinculos(SESSAO_A, ALFA)
        self.assertTrue(self.banco.delete_session(SESSAO_A, user_id=ALFA))
        ids = [memoria.memory_id for memoria in self.banco.get_user_memories(user_id=ALFA)]
        self.banco.delete_user_memories(ids, user_id=ALFA)
        residuos_a = self.contar_residuos(MARCADOR_A)
        residuos_b = self.contar_residuos(MARCADOR_B)
        self.assertEqual(residuos_a, dict.fromkeys(esperado, 0))
        self.assertEqual(residuos_b, esperado)
        print(json.dumps({"G": {"titular_removido": residuos_a, "outro_titular": residuos_b}}), flush=True)

    def excluir(self, matricula=VALIDA_A, **caminhos):
        from barreira_persistente import BarreiraPersistente
        from exclusao_memoria import excluir_memoria_titular

        if not hasattr(self, "barreira"):
            self.barreira = BarreiraPersistente(secrets.token_bytes(32))

        return excluir_memoria_titular(
            matricula, barreira=self.barreira,
            **({"caminho_banco": self.caminho, "banco_autorizado": self.caminho} | caminhos),
        )

    def criar_titulares_validos(self):
        from agno.db.schemas.memory import UserMemory

        for sessao, titular, marcador in (
            (SESSAO_A, VALIDA_A, MARCADOR_A), (SESSAO_B, VALIDA_B, MARCADOR_B),
        ):
            self.criar_sessao(sessao, titular, marcador)
            self.criar_run(sessao, titular, marcador, f"run-{sessao}")
            self.assertIsNotNone(self.banco.upsert_user_memory(
                UserMemory(memory=marcador, input=marcador, user_id=titular)
            ))

    def test_servico_exclui_e_repete_preservando_outro_titular(self):
        self.criar_titulares_validos()
        outro = self.inventario(VALIDA_B)
        resultado = self.excluir()
        self.assertEqual(resultado["status"], "excluido", resultado["conflitos"])
        self.assertEqual(resultado["antes"], {"sessoes": 1, "execucoes": 1, "memorias": 1})
        self.assertEqual(resultado["depois"], {"sessoes": 0, "execucoes": 0, "memorias": 0})
        self.assertEqual((resultado["sessoes_verificadas"], resultado["memorias_verificadas"]), (2, 2))
        self.assertFalse(resultado["nome_verificado"])
        self.assertTrue(resultado["revisao_manual"])
        self.assertTrue(self.inventario(VALIDA_B) == outro)
        self.assertEqual(self.excluir()["status"], "sem_registros")
        serializado = json.dumps(resultado)
        self.assertTrue(all(valor not in serializado for valor in (
            VALIDA_A, VALIDA_B, MARCADOR_A, MARCADOR_B, SESSAO_A, SESSAO_B, str(self.caminho),
        )))

    def test_servico_bloqueia_vinculos_divergentes_e_nulos(self):
        self.criar_titulares_validos()
        self.criar_run(SESSAO_A, VALIDA_B, MARCADOR_B, RUN_DIVERGENTE)
        self.criar_run(SESSAO_A, None, MARCADOR_B, "run-titular-nulo")
        self.criar_sessao("diligencia-sem-titular", None, MARCADOR_A)
        primeiro = self.inventario(VALIDA_A)
        outro = self.inventario(VALIDA_B)
        with patch.object(type(self.banco), "delete_session") as apagar_sessao, patch.object(
            type(self.banco), "delete_user_memories",
        ) as apagar_memorias:
            resultado = self.excluir()
            apagar_sessao.assert_not_called()
            apagar_memorias.assert_not_called()
        self.assertEqual(resultado["status"], "bloqueado")
        self.assertEqual(resultado["conflitos"]["titular_da_execucao_incompativel"], 2)
        self.assertEqual(resultado["conflitos"]["sessao_sem_titular"], 1)
        self.assertTrue(self.inventario(VALIDA_A) == primeiro)
        self.assertTrue(self.inventario(VALIDA_B) == outro)

    def test_servico_exclui_memoria_sem_sessao(self):
        from agno.db.schemas.memory import UserMemory

        self.assertIsNotNone(self.banco.upsert_user_memory(UserMemory(memory=MARCADOR_A, user_id=VALIDA_A)))
        self.assertIsNotNone(self.banco.upsert_user_memory(UserMemory(memory=MARCADOR_B, user_id=VALIDA_B)))
        outro = self.inventario(VALIDA_B)
        resultado = self.excluir()
        self.assertEqual(resultado["status"], "excluido", resultado["conflitos"])
        self.assertEqual(resultado["antes"], {"sessoes": 0, "execucoes": 0, "memorias": 1})
        self.assertEqual(resultado["depois"], {"sessoes": 0, "execucoes": 0, "memorias": 0})
        self.assertTrue(self.inventario(VALIDA_B) == outro)

    def test_servico_bloqueia_esquema_fora_da_conferencia(self):
        self.criar_titulares_validos()
        with closing(sqlite3.connect(self.caminho)) as conexao, conexao:
            conexao.execute("CREATE TABLE sqliteAuxiliarSintetica (conteudo TEXT)")
        with patch.object(type(self.banco), "delete_session") as apagar:
            resultado = self.excluir()
            apagar.assert_not_called()
        self.assertEqual(resultado["conflitos"], {"esquema_nao_suportado": 1})
        self.assertEqual(tuple(map(len, self.inventario(VALIDA_A))), (1, 1, 1))

    def test_servico_recusa_0112_sem_confirmacao(self):
        self.criar_sessao("DIA-2026-0112", VALIDA_A, MARCADOR_A)
        inicial = self.excluir()
        self.assertEqual(inicial["conflitos"], {"titular_da_complementacao_nao_confirmado": 1})

    def test_servico_0111_e_0112_confirmados(self):
        from ferramentas import consultar_servidor
        from persistencia_sessoes import registrar_complementacao, registrar_diligencia

        self.criar_titulares_validos()
        titulares = {}
        for protocolo in ("DIA-2026-0111", "DIA-2026-0112"):
            registrar_diligencia(protocolo, caminho_banco=self.caminho)
            corrigida = registrar_complementacao(protocolo, caminho_banco=self.caminho)
            titulares[protocolo] = corrigida.user_id
            self.criar_run(protocolo, corrigida.user_id, MARCADOR_A, f"run-{protocolo}")
        nomes = [consultar_servidor(titular)["nome"] for titular in titulares.values()]
        documento = json.dumps({"referencias": [{"nome": "  ".join(nome.upper().split())} for nome in nomes]})
        with closing(sqlite3.connect(self.caminho)) as conexao, conexao:
            conexao.execute("UPDATE agno_sessions SET metadata = ? WHERE user_id = ?", (documento, VALIDA_B))
            conexao.execute("UPDATE agno_memories SET input = ? WHERE user_id = ?", (documento, VALIDA_B))
            dados_run = json.loads(conexao.execute(
                "SELECT run_data FROM agno_runs WHERE user_id = ?", (VALIDA_B,),
            ).fetchone()[0])
            dados_run["referencias_administrativas"] = documento
            conexao.execute("UPDATE agno_runs SET run_data = ? WHERE user_id = ?", (json.dumps(dados_run), VALIDA_B))
        outros = self.inventario(VALIDA_B)
        for protocolo, titular in titulares.items():
            resultado = self.excluir(matricula=titular)
            self.assertEqual(resultado["status"], "excluido", resultado["conflitos"])
            self.assertEqual(resultado["antes"]["sessoes"], 1)
            self.assertIsNone(self.banco.get_session(protocolo))
            self.assertTrue(resultado["nome_verificado"])
            self.assertEqual(resultado["residuos"], {"agno_sessions": 1, "agno_runs": 1, "agno_memories": 1})
            self.assertTrue(resultado["revisao_manual"])
            self.assertFalse(any(nome in json.dumps(resultado) for nome in nomes))
            self.assertTrue(self.inventario(VALIDA_B) == outros)

    def test_servico_reporta_mencao_sem_atribuir_propriedade(self):
        self.criar_titulares_validos()
        self.criar_run(SESSAO_B, VALIDA_B, f"Marcador que menciona {VALIDA_A}", "run-mencao")
        with closing(sqlite3.connect(self.caminho)) as conexao, conexao:
            conexao.execute("UPDATE agno_memories SET input = ? WHERE user_id = ?",
                            (f"Menção literal à matrícula {VALIDA_A}.", VALIDA_B))
        outro = self.inventario(VALIDA_B)
        resultado = self.excluir()
        self.assertEqual(resultado["status"], "excluido")
        esperado = {"agno_runs": 1, "agno_memories": 1}
        self.assertEqual(resultado["residuos"], esperado)
        self.assertTrue(resultado["revisao_manual"])
        self.assertTrue(self.inventario(VALIDA_B) == outro)
        repetida = self.excluir()
        self.assertEqual(repetida["status"], "sem_registros")
        self.assertEqual(repetida["residuos"], esperado)
        self.assertNotIn(VALIDA_A, json.dumps(repetida))

    def test_servico_detecta_escapes_em_json_aninhado_e_no_input(self):
        self.criar_titulares_validos()
        escape = "".join(f"\\u{ord(digito):04x}" for digito in VALIDA_A)
        documento = '{"niveis":[{"referencias":[{"titular":"' + escape + '"}]}]}'
        with closing(sqlite3.connect(self.caminho)) as conexao, conexao:
            conexao.execute("UPDATE agno_sessions SET metadata = ? WHERE session_id = ?",
                            (documento, SESSAO_B))
            # JSON dentro de um campo TEXT e JSON serializado dentro de uma string JSON.
            conexao.execute("UPDATE agno_memories SET memory = ?, input = ? WHERE user_id = ?",
                            (json.dumps(documento), documento, VALIDA_B))
            run_id, original = conexao.execute(
                "SELECT run_id, run_data FROM agno_runs WHERE user_id = ?", (VALIDA_B,),
            ).fetchone()
            run_data = original.rstrip()[:-1] + ',"documento":' + documento + '}'
            conexao.execute("UPDATE agno_runs SET run_data = ? WHERE run_id = ?", (run_data, run_id))
        self.assertNotIn(VALIDA_A, documento)

        outro = self.inventario(VALIDA_B)
        resultado = self.excluir()
        esperado = {"agno_sessions": 1, "agno_runs": 1, "agno_memories": 1}
        self.assertEqual(resultado["status"], "excluido")
        self.assertEqual(resultado["residuos"], esperado)
        self.assertTrue(resultado["revisao_manual"])
        self.assertTrue(self.inventario(VALIDA_B) == outro)
        self.assertNotIn(VALIDA_A, json.dumps(resultado))
        self.assertEqual(self.excluir()["residuos"], esperado)
        print(json.dumps({"json_aninhado": esperado}), flush=True)

    def test_servico_bloqueia_inspecao_de_json_invalido_e_campo_binario(self):
        self.criar_titulares_validos()
        with closing(sqlite3.connect(self.caminho)) as conexao, conexao:
            conexao.execute("UPDATE agno_sessions SET metadata = ? WHERE user_id = ?", ('{"objeto":', VALIDA_B))
            conexao.execute("UPDATE agno_memories SET input = ? WHERE user_id = ?", (b"binario-sintetico", VALIDA_B))
        with patch.object(type(self.banco), "delete_session") as sessoes, patch.object(
            type(self.banco), "delete_user_memories",
        ) as memorias:
            relatorio = self.excluir()
            sessoes.assert_not_called()
            memorias.assert_not_called()
        self.assertEqual(relatorio["status"], "bloqueado")
        self.assertEqual(relatorio["conflitos"], {"inspecao_residuos_incompleta": 2})
        self.assertTrue(relatorio["revisao_manual"])
        self.assertEqual(relatorio["antes"], relatorio["depois"])
        self.assertEqual(tuple(map(len, self.inventario(VALIDA_A))), (1, 1, 1))

    def test_servico_bloqueia_legado_e_orfao(self):
        self.criar_titulares_validos()
        legado = self.criar_run(SESSAO_A, VALIDA_A, MARCADOR_A, "run-legado-servico")
        with closing(sqlite3.connect(self.caminho)) as conexao, conexao:
            conexao.execute("PRAGMA foreign_keys = OFF")
            conexao.execute("ALTER TABLE agno_sessions ADD COLUMN runs JSON")
            conexao.execute("UPDATE agno_sessions SET runs = ? WHERE session_id = ?",
                            (json.dumps([legado.to_dict()]), SESSAO_B))
            conexao.execute("UPDATE agno_runs SET session_id = ? WHERE run_id = ?",
                            ("sessao-inexistente", legado.run_id))
        resultado = self.excluir()
        self.assertEqual(resultado["status"], "bloqueado")
        self.assertEqual(resultado["conflitos"]["historico_legado_nao_resolvido"], 1)
        self.assertEqual(resultado["conflitos"]["execucao_orfa"], 1)
        self.assertTrue(resultado["revisao_manual"])

    def test_servico_recusa_caminho_matricula_e_banco_historico(self):
        self.criar_titulares_validos()
        outro_caminho = self.caminho.with_name("outro.db")
        historico = self.caminho.with_name("cenario_B.db")
        historico.touch()
        recusas = (
            self.excluir(caminho_banco=outro_caminho),
            self.excluir(caminho_banco=historico, banco_autorizado=historico),
            self.excluir(matricula="matricula-invalida"),
        )
        self.assertTrue(all(resultado["status"] == "bloqueado" for resultado in recusas))
        self.assertFalse(outro_caminho.exists())
        self.assertEqual(historico.stat().st_size, 0)
        self.assertEqual(tuple(map(len, self.inventario(VALIDA_A))), (1, 1, 1))

    def test_servico_reverte_exclusao_quando_memorias_falham(self):
        self.criar_titulares_validos()
        antes = (self.inventario(VALIDA_A), self.inventario(VALIDA_B))
        excluir_memorias = type(self.banco).delete_user_memories

        def falhar_depois_de_excluir(banco, ids, *, user_id):
            self.assertFalse(banco.get_sessions(user_id=user_id))
            excluir_memorias(banco, ids, user_id=user_id)
            self.assertFalse(banco.get_user_memories(user_id=user_id))
            raise RuntimeError(MARCADOR_A)

        with patch.object(type(self.banco), "delete_user_memories", falhar_depois_de_excluir):
            resultado = self.excluir()
        self.assertEqual(resultado["status"], "erro")
        self.assertEqual(resultado["conflitos"], {"exclusao_revertida": 1})
        self.assertEqual(resultado["depois"], resultado["antes"])
        self.assertTrue((self.inventario(VALIDA_A), self.inventario(VALIDA_B)) == antes)
        self.assertNotIn(MARCADOR_A, json.dumps(resultado))

    def test_servico_bloqueia_concorrencia_antes_e_durante_exclusao(self):
        self.criar_titulares_validos()
        with closing(sqlite3.connect(self.caminho, timeout=0)) as concorrente:
            concorrente.execute("BEGIN IMMEDIATE")
            resultado = self.excluir()
            self.assertEqual(resultado["status"], "bloqueado")
            self.assertEqual(resultado["conflitos"], {"escrita_concorrente": 1})
            concorrente.rollback()
            excluir_sessao = type(self.banco).delete_session

            def tentar_escrita(banco, session_id, *, user_id):
                with self.assertRaisesRegex(sqlite3.OperationalError, "locked"):
                    concorrente.execute("BEGIN IMMEDIATE")
                return excluir_sessao(banco, session_id, user_id=user_id)

            with patch.object(type(self.banco), "delete_session", tentar_escrita):
                self.assertEqual(self.excluir()["status"], "excluido")
        self.assertEqual(tuple(map(len, self.inventario(VALIDA_B))), (1, 1, 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
