"""Barreira de escrita da cópia de trabalho SQLite, com chave fornecida pelo servidor."""

import hmac
import re
import sqlite3
from contextlib import closing, contextmanager
from importlib.metadata import version
from pathlib import Path
from stat import S_ISREG

from agno.db.sqlite import SqliteDb
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool


_DADOS = {"agno_sessions": "session_id", "agno_runs": "run_id", "agno_memories": "memory_id"}
TABELAS_AGNO = frozenset((*_DADOS, "agno_schema_versions"))
_BASE = Path(__file__).resolve().parent
_TRABALHO = _BASE / "resultados" / "sessoes_interativas.db"
_ESTADOS = {"bloqueio_pendente", "concluida", "revisao_manual"}
_DDL = {
    ("table", "barreira_config"): (
        "CREATE TABLE barreira_config (id INTEGER PRIMARY KEY CHECK (id = 1), verificador BLOB NOT NULL)"
    ),
    ("table", "barreira_restricoes"): (
        "CREATE TABLE barreira_restricoes (titular BLOB PRIMARY KEY NOT NULL, "
        "estado TEXT NOT NULL CHECK (estado IN ('bloqueio_pendente', 'concluida', 'revisao_manual')))"
    ),
    ("table", "barreira_protocolos"): (
        "CREATE TABLE barreira_protocolos (protocolo BLOB PRIMARY KEY NOT NULL, titular BLOB NOT NULL)"
    ),
}


def _gatilho(tabela, operacao):
    regras = [
        "SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM barreira_config "
        "WHERE id = 1 AND verificador = barreira_chave('config', 'v1')) "
        "THEN RAISE(ABORT, 'barreira_indisponivel') END;"
    ]
    chaves = {}
    for linha in ("NEW", "OLD") if operacao == "UPDATE" else ("NEW",):
        titular = f"barreira_chave('titular', {linha}.user_id)"
        if tabela != "agno_memories":
            vinculo = "(SELECT titular FROM barreira_protocolos WHERE protocolo = " + (
                f"barreira_chave('protocolo', {linha}.session_id))"
            )
            regras.append(
                f"SELECT CASE WHEN {vinculo} IS NOT NULL AND {titular} IS NOT NULL "
                f"AND {vinculo} IS NOT {titular} THEN RAISE(ABORT, 'barreira_vinculo') END;"
            )
            if tabela == "agno_sessions":
                titular = f"COALESCE({titular}, {vinculo})"
            else:
                regras.append(
                    "SELECT CASE WHEN NOT EXISTS (SELECT 1 FROM agno_sessions s "
                    f"WHERE s.session_id = {linha}.session_id AND s.user_id = {linha}.user_id) "
                    "THEN RAISE(ABORT, 'barreira_vinculo') END;"
                )
                regras.append(
                    f"SELECT CASE WHEN NOT json_valid({linha}.run_data) "
                    "THEN RAISE(ABORT, 'barreira_vinculo') END;"
                )
                regras.append(
                    f"SELECT CASE WHEN json_extract({linha}.run_data, '$.user_id') IS NOT {linha}.user_id "
                    f"OR json_extract({linha}.run_data, '$.session_id') IS NOT {linha}.session_id "
                    f"OR json_extract({linha}.run_data, '$.run_id') IS NOT {linha}.run_id "
                    "THEN RAISE(ABORT, 'barreira_vinculo') END;"
                )
        chaves[linha] = titular
        regras.append(
            f"SELECT CASE WHEN {titular} IS NULL OR barreira_admissao({titular}) IS NOT 0 "
            f"OR EXISTS (SELECT 1 FROM barreira_restricoes WHERE titular = {titular}) "
            "THEN RAISE(ABORT, 'barreira_bloqueada') END;"
        )
    if operacao == "UPDATE":
        pk = _DADOS[tabela]
        regras.append(
            f"SELECT CASE WHEN OLD.{pk} IS NOT NEW.{pk} OR {chaves['OLD']} IS NOT {chaves['NEW']} "
            "THEN RAISE(ABORT, 'barreira_vinculo') END;"
        )
    else:
        pk = _DADOS[tabela]
        regras.append(
            f"SELECT CASE WHEN EXISTS (SELECT 1 FROM {tabela} WHERE {pk} = NEW.{pk} "
            f"AND {tabela}.user_id IS NOT NEW.user_id) THEN RAISE(ABORT, 'barreira_vinculo') END;"
        )
    nome = f"barreira_{tabela}_{operacao.lower()}"
    return nome, f"CREATE TRIGGER {nome} BEFORE {operacao} ON {tabela} BEGIN {' '.join(regras)} END"


for _tabela in _DADOS:
    for _operacao in ("INSERT", "UPDATE"):
        _nome, _sql = _gatilho(_tabela, _operacao)
        _DDL["trigger", _nome] = _sql


def caminho_validado(caminho, autorizado):
    if not isinstance(caminho, Path) or not isinstance(autorizado, Path):
        return None
    if not caminho.is_absolute() or caminho != autorizado or ".." in caminho.parts:
        return None
    if caminho.is_relative_to(_BASE) and caminho != _TRABALHO:
        return None
    if (
        caminho.name.casefold() in {"agente_sessoes.db", "cenario_b.db", "cenario_c.db"}
        or any(parte.casefold() == "experimentos_memoria" for parte in caminho.parts)
    ):
        return None
    try:
        if caminho.parent.resolve(strict=True) != caminho.parent or caminho.is_symlink():
            return None
        real = caminho.resolve(strict=True)
        if real != caminho:
            return None
        estado = real.stat()
        if not S_ISREG(estado.st_mode) or estado.st_nlink != 1:
            return None
    except (OSError, RuntimeError):
        return None
    return real


def reservar_escrita(conexao):
    conexao.exec_driver_sql("PRAGMA foreign_keys = ON")
    conexao.exec_driver_sql("BEGIN IMMEDIATE")
    if conexao.exec_driver_sql("PRAGMA foreign_keys").scalar_one() != 1:
        raise RuntimeError("coordenacao_indisponivel")


def exige_admissao(caminho):
    if caminho is None or not caminho.is_file():
        return False
    with closing(sqlite3.connect(caminho.as_uri() + "?mode=ro", uri=True, timeout=0)) as conexao:
        return conexao.execute(
            "SELECT 1 FROM sqlite_schema WHERE type IN ('table', 'trigger') AND name GLOB 'barreira_*' LIMIT 1"
        ).fetchone() is not None


def conferir_esquema(conexao, *, permitir_ausente=False):
    objetos = {
        (tipo, nome): sql for tipo, nome, sql in conexao.exec_driver_sql(
            "SELECT type, name, sql FROM main.sqlite_schema "
            "WHERE type IN ('table', 'trigger') AND name NOT GLOB 'sqlite_*'"
        )
    }
    auxiliares = {obj: sql for obj, sql in objetos.items() if obj not in {
        ("table", nome) for nome in TABELAS_AGNO
    }}
    if permitir_ausente and not auxiliares:
        return False
    if auxiliares != _DDL or any(("table", nome) not in objetos for nome in _DADOS):
        raise ValueError("esquema_nao_suportado")
    return True


@contextmanager
def adaptar_agno(engine, conexao):
    banco = SqliteDb(db_engine=engine)
    banco.db_engine = conexao
    banco.Session.configure(bind=conexao, join_transaction_mode="create_savepoint")
    try:
        yield banco
    finally:
        banco.Session.remove()


class BarreiraPersistente:
    """O mesmo segredo deve ser fornecido por configuração confiável após reiniciar.

    A admissão é vinculada a um titular. Esta versão não oferece desbloqueio.
    """

    def __init__(self, segredo):
        if not isinstance(segredo, bytes) or len(segredo) < 32:
            raise ValueError("chave_da_barreira_invalida")
        self.__segredo = segredo

    def _chave(self, dominio, valor):
        if not isinstance(valor, str) or not valor:
            return None
        return hmac.digest(self.__segredo, f"barreira-v1:{dominio}:{valor}".encode(), "sha256")

    def _engine(self, caminho, *, admitido=None):
        uri = caminho.as_uri() + "?mode=rw"

        def conectar():
            conexao = sqlite3.connect(uri, uri=True, timeout=0)
            conexao.create_function("barreira_chave", 2, self._chave)
            conexao.create_function("barreira_admissao", 1, lambda chave: 0 if chave == admitido else None)
            return conexao

        return create_engine("sqlite://", creator=conectar, poolclass=NullPool, hide_parameters=True)

    def conferir_chave(self, conexao):
        atual = conexao.exec_driver_sql("SELECT verificador FROM barreira_config WHERE id = 1").scalar()
        if not isinstance(atual, bytes) or not hmac.compare_digest(atual, self._chave("config", "v1")):
            raise ValueError("chave_da_barreira_incompativel")

    def preparar_na_transacao(self, conexao, banco):
        if not conferir_esquema(conexao, permitir_ausente=True):
            for tipo in ("sessions", "runs", "memories"):
                if banco._get_table(tipo, create_table_if_not_found=True) is None:
                    raise RuntimeError("esquema_agno_indisponivel")
            for sql in _DDL.values():
                conexao.exec_driver_sql(sql)
            conexao.exec_driver_sql(
                "INSERT INTO barreira_config VALUES (1, ?)", (self._chave("config", "v1"),),
            )
        conferir_esquema(conexao)
        self.conferir_chave(conexao)

    def registrar_pendente(self, conexao, matricula):
        conexao.exec_driver_sql(
            "INSERT INTO barreira_restricoes VALUES (?, 'bloqueio_pendente') "
            "ON CONFLICT (titular) DO NOTHING",
            (self._chave("titular", matricula),),
        )

    def registrar_estado(self, conexao, matricula, estado):
        if estado not in _ESTADOS:
            raise ValueError("estado_da_barreira_invalido")
        resultado = conexao.exec_driver_sql(
            "UPDATE barreira_restricoes SET estado = ? WHERE titular = ?",
            (estado, self._chave("titular", matricula)),
        )
        if resultado.rowcount != 1:
            raise RuntimeError("restricao_ausente")

    def conferir_protocolos(self, conexao, sessoes):
        for sessao in sessoes:
            chave = self._chave("protocolo", sessao["session_id"])
            atual = conexao.exec_driver_sql(
                "SELECT titular FROM barreira_protocolos WHERE protocolo = ?", (chave,),
            ).scalar()
            if atual is not None and atual != self._chave("titular", sessao["user_id"]):
                return False
        return True

    def vincular_verificados(self, conexao, sessoes, matricula):
        if sessoes:
            conexao.exec_driver_sql(
                "INSERT INTO barreira_protocolos VALUES (?, ?) ON CONFLICT (protocolo) DO NOTHING",
                [(self._chave("protocolo", sessao["session_id"]), self._chave("titular", matricula))
                 for sessao in sessoes],
            )

    def preparar(self, *, caminho_banco, banco_autorizado):
        """Instala a barreira no banco autorizado antes de admitir os escritores."""
        caminho = caminho_validado(caminho_banco, banco_autorizado)
        if caminho is None or version("agno") != "3.2.1":
            raise ValueError("banco_ou_adaptador_nao_autorizado")
        engine = self._engine(caminho)
        try:
            with engine.begin() as conexao:
                reservar_escrita(conexao)
                with adaptar_agno(engine, conexao) as banco:
                    self.preparar_na_transacao(conexao, banco)
        finally:
            engine.dispose()

    def vincular_protocolo_validado(self, protocolo, matricula, *, caminho_banco, banco_autorizado):
        """Recebe o vínculo já comprovado pelo servidor. Não altera o titular da sessão."""
        caminho = caminho_validado(caminho_banco, banco_autorizado)
        if (
            caminho is None or not isinstance(protocolo, str) or not protocolo
            or not isinstance(matricula, str) or re.fullmatch(r"[0-9]{6}", matricula) is None
        ):
            raise ValueError("vinculo_invalido")
        engine = self._engine(caminho)
        try:
            with engine.begin() as conexao:
                reservar_escrita(conexao)
                conferir_esquema(conexao)
                self.conferir_chave(conexao)
                sessao = {"session_id": protocolo, "user_id": matricula}
                atual = conexao.exec_driver_sql(
                    "SELECT user_id FROM agno_sessions WHERE session_id = ?", (protocolo,),
                ).scalar()
                if atual not in (None, matricula) or not self.conferir_protocolos(conexao, [sessao]):
                    raise ValueError("protocolo_com_vinculo_divergente")
                self.vincular_verificados(conexao, [sessao], matricula)
        finally:
            engine.dispose()

    def confirmar_admissao(self, banco, matricula):
        with banco.db_engine.connect() as conexao:
            self._conferir_admissao(conexao, self._chave("titular", matricula))

    def _conferir_admissao(self, conexao, titular):
        conferir_esquema(conexao)
        self.conferir_chave(conexao)
        if conexao.exec_driver_sql(
            "SELECT 1 FROM barreira_restricoes WHERE titular = ?", (titular,),
        ).scalar():
            raise PermissionError("barreira_bloqueada")

    @contextmanager
    def abrir_agno(self, matricula, *, caminho_banco, banco_autorizado):
        """Admite antes do trabalho e captura a autorização nas conexões do Agno."""
        caminho = caminho_validado(caminho_banco, banco_autorizado)
        if caminho is None or not isinstance(matricula, str) or re.fullmatch(r"[0-9]{6}", matricula) is None:
            raise ValueError("admissao_invalida")
        if version("agno") != "3.2.1":
            raise ValueError("adaptador_nao_validado")
        titular = self._chave("titular", matricula)
        engine = self._engine(caminho, admitido=titular)
        try:
            with engine.connect() as conexao:
                self._conferir_admissao(conexao, titular)
            banco = SqliteDb(db_engine=engine, db_file=str(caminho))
            try:
                yield banco
            finally:
                banco.close()
        finally:
            engine.dispose()
