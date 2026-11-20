import json
import time
from pathlib import Path

import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from agente import criar_agente, preparar_entrada
from modelos import Instrucao

print("=" * 70)
print("PRIMEIRA EXECUCAO REAL - AGENTE DE DIARIAS")
print("=" * 70)

numero = "DIA-2026-0101"

agente, pedido = criar_agente(
    numero,
    usar_memoria=False,
    chamadas_paralelas=False,
)

entrada = preparar_entrada(pedido)

print("Pedido:", numero)
print("Modelo:", agente.model.id)
print("Memoria: desativada")
print("Paralelismo: desativado")
print("Iniciando chamada real a OpenAI...")

inicio = time.perf_counter()

try:
    resposta = agente.run(
        entrada,
        session_id=numero,
        user_id=str(pedido["matricula"]),
    )

    duracao = time.perf_counter() - inicio

    print("\n=== RESULTADO DA EXECUCAO ===")
    print("Status:", resposta.status)
    print("Tempo (segundos):", round(duracao, 2))

    from agno.run.agent import RunStatus

    if resposta.status != RunStatus.completed:
        raise RuntimeError(
            "Execucao nao concluida. "
            f"Status recebido: {resposta.status}. "
            "Verifique os logs da API."
        )

    conteudo = resposta.content

    if isinstance(conteudo, Instrucao):
        instrucao = conteudo
    elif isinstance(conteudo, dict):
        instrucao = Instrucao.model_validate(conteudo)
    elif isinstance(conteudo, str):
        instrucao = Instrucao.model_validate_json(conteudo)
    else:
        raise TypeError(
            f"Tipo de resposta inesperado: {type(conteudo)}"
        )

    print("Estrutura Pydantic: VALIDA")
    print("Numero:", instrucao.numero_pedido)
    print("Recomendacao:", instrucao.recomendacao)
    print("Quantidade de diarias:", instrucao.quantidade_diarias)
    print("Valor total:", instrucao.valor_total)
    print("Verificacoes:", len(instrucao.verificacoes))
    print("Exige autorizacao superior:", instrucao.exige_autorizacao_superior)

    print("\n=== VERIFICACOES ===")

    for verificacao in instrucao.verificacoes:
        print(
            f"{verificacao.criterio}: "
            f"{verificacao.situacao}"
        )

    print("\n=== METRICAS ===")

    if resposta.metrics:
        print("Metricas:", resposta.metrics)

    print("\n=== FERRAMENTAS EXECUTADAS ===")

    chamadas = []

    for ferramenta in (resposta.tools or []):
        nome = getattr(
            ferramenta,
            "tool_name",
            getattr(ferramenta, "name", "desconhecida"),
        )

        argumentos = getattr(
            ferramenta,
            "tool_args",
            getattr(ferramenta, "arguments", None),
        )

        erro = getattr(ferramenta, "tool_call_error", None)

        chamadas.append({
            "nome": str(nome),
            "argumentos": argumentos,
            "erro": str(erro) if erro else None,
        })

        print("Ferramenta:", nome)
        print("Argumentos:", argumentos)
        print("Erro:", erro)

    print("Total de chamadas:", len(chamadas))

    resultado = {
        "numero_pedido": numero,
        "modelo": agente.model.id,
        "duracao_segundos": round(duracao, 4),
        "status": str(resposta.status),
        "instrucao": instrucao.model_dump(),
        "ferramentas": chamadas,
        "total_chamadas_ferramentas": len(chamadas),
    }

    destino = Path("resultados/primeira_execucao.json")
    destino.parent.mkdir(exist_ok=True)

    destino.write_text(
        json.dumps(
            resultado,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\nResultado salvo:", destino)

except Exception as erro:
    print("\nERRO NA EXECUCAO")
    print("Tipo:", type(erro).__name__)
    print("Detalhes:", str(erro)[:500])
    raise
