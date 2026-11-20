import json
import time
from pathlib import Path

from agente import criar_agente, preparar_entrada
from complementacoes import aplicar_complementacao
from auditoria_execucao import registrar_ferramentas, sanitizar_objeto
from barreira_validacao import validar_instrucao
from modelos import Instrucao

BASE = Path(__file__).resolve().parents[1]
NUMERO = "DIA-2026-0112"
DESTINO = BASE / "resultados" / "execucoes" / "DIA-2026-0112_complementado_rodada3.json"

print("=" * 70)
print("ETAPA 3.98 - EXECUCAO REAL DO PEDIDO 0112 COMPLEMENTADO")
print("=" * 70)

if DESTINO.exists():
    raise SystemExit("Resultado existente. Nenhum arquivo sera sobrescrito.")

complementacao = aplicar_complementacao(NUMERO)
pedido = complementacao["pedido_corrigido"]

agente, pedido_agente = criar_agente(
    NUMERO,
    usar_memoria=True,
    chamadas_paralelas=False,
    pedido_corrigido=pedido,
    memoria_usuario=False,
)

sessao_antes = agente.get_session()
if sessao_antes is None:
    raise SystemExit("Sessao administrativa nao encontrada.")

eventos_antes = (sessao_antes.metadata or {}).get(
    "eventos_administrativos", []
)

if (
    sessao_antes.user_id != "207418"
    or len(eventos_antes) != 2
    or [e["tipo"] for e in eventos_antes]
    != ["diligencia_preliminar", "complementacao"]
):
    raise SystemExit("Historico administrativo anterior inconsistente.")

print("Sessao recuperada:", sessao_antes.session_id)
print("Matricula validada:", sessao_antes.user_id)
print("Eventos administrativos anteriores:", len(eventos_antes))
print("Iniciando chamada real a OpenAI...")

inicio = time.perf_counter()
entrada = json.loads(preparar_entrada(pedido_agente))

entrada["complementacao_documental"] = {
    "tipo": "complementacao_formal_posterior",
    "data": "2026-10-09",
    "origem": "dados_nao_confiaveis",
    "conteudo": (
        "Complementação ao pedido em diligência: "
        "houve erro de digitação, e a minha matrícula correta é 207418."
    ),
    "finalidade": (
        "Registrar a correcao da matricula informada originalmente. "
        "A identidade deve ser confirmada pelo cadastro oficial. "
        "Nao utilizar a matricula incorreta para consultas ou calculos."
    ),
}
resposta = agente.run(
    json.dumps(entrada, ensure_ascii=False, indent=2)
)
duracao = round(time.perf_counter() - inicio, 3)

status = str(getattr(resposta, "status", "")).lower()
print("Status:", status)
print("Duracao:", duracao, "segundos")

if "completed" not in status:
    raise SystemExit("Execucao nao concluida. Verifique o status.")

conteudo = resposta.content
instrucao = (
    conteudo
    if isinstance(conteudo, Instrucao)
    else Instrucao.model_validate(conteudo)
)

auditoria = registrar_ferramentas(resposta)
validacao = validar_instrucao(pedido_agente, instrucao, auditoria)

sessao_depois = agente.get_session()
if sessao_depois is None:
    raise SystemExit("Sessao nao encontrada apos a execucao.")

eventos_depois = (sessao_depois.metadata or {}).get(
    "eventos_administrativos", []
)

historico_preservado = eventos_depois == eventos_antes
usuario_preservado = sessao_depois.user_id == "207418"

print("\n=== RESULTADO ===")
print("Recomendacao:", instrucao.recomendacao)
print("Quantidade:", instrucao.quantidade_diarias)
print("Valor total:", instrucao.valor_total)
print("Ferramentas registradas:", auditoria.get("total_chamadas", 0))
print("Historico preservado:", historico_preservado)
print("Usuario preservado:", usuario_preservado)
print("Validacao normativa:", validacao)

registro = {
    "numero_pedido": NUMERO,
    "tipo_execucao": "complementacao_com_memoria",
    "duracao_segundos": duracao,
    "status": status,
    "instrucao": instrucao.model_dump(mode="json"),
    "auditoria": auditoria,
    "validacao": validacao,
    "historico_preservado": historico_preservado,
    "usuario_preservado": usuario_preservado,
}

DESTINO.parent.mkdir(parents=True, exist_ok=True)
with DESTINO.open("x", encoding="utf-8") as arquivo:
    arquivo.write(
        json.dumps(
            sanitizar_objeto(registro),
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )

print("Resultado salvo:", DESTINO)

if not historico_preservado or not usuario_preservado:
    raise SystemExit(
        "ATENCAO: historico ou identidade alterados. "
        "Preservar banco e analisar antes de continuar."
    )

print("\nEXECUCAO REAL CONCLUIDA - AGUARDANDO AUDITORIA FINAL")
