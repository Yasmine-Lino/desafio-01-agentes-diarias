import argparse
import json
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from agno.run.agent import RunStatus

from agente import criar_agente, preparar_entrada, obter_pedido
from validacao_pedido import validar_pedido
from diligencia_preliminar import criar_instrucao_diligencia
from auditoria_execucao import (
    registrar_ferramentas,
    imprimir_auditoria_ferramentas,
    sanitizar_objeto,
)
from barreira_validacao import validar_instrucao
from modelos import Instrucao


def executar(numero):
    """Executa um pedido e valida as evidencias antes da persistencia."""

    destino = (
        BASE / "resultados" / "execucoes" / f"{numero}.json"
    )

    if destino.exists():
        raise FileExistsError(
            "Resultado ja existente. Arquivo preservado: "
            + str(destino)
        )

    pedido = obter_pedido(numero)
    validacao_preliminar = validar_pedido(pedido)

    if not validacao_preliminar["pode_analisar_merito"]:
        print("=" * 70)
        print("DILIGENCIA PRELIMINAR - DESAFIO 01")
        print("=" * 70)
        print("Pedido:", numero)
        print("Modelo: nao utilizado")
        print("Memoria: desativada")
        print("Paralelismo: nao utilizado")
        print("Chamada a OpenAI: nao realizada")

        instrucao = criar_instrucao_diligencia(pedido)
        auditoria = {"chamadas": []}

        barreira = validar_instrucao(
            pedido,
            instrucao,
            auditoria,
        )

        print("\n=== BARREIRA INDEPENDENTE ===")
        print("Aprovado:", barreira["aprovado"])
        print("Mensagem:", barreira["mensagem"])

        for erro in barreira["erros"]:
            print("BLOQUEIO:", erro)

        resultado = {
            "numero_pedido": numero,
            "tipo_execucao": "diligencia_preliminar",
            "modelo": None,
            "duracao_segundos": None,
            "status": "diligencia_preliminar_concluida",
            "instrucao": sanitizar_objeto(
                instrucao.model_dump()
            ),
            "auditoria_ferramentas": auditoria,
            "barreira_validacao": barreira,
            "metricas": None,
            "aprovado_para_revisao_humana": barreira["aprovado"],
        }

        destino.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with destino.open("x", encoding="utf-8") as arquivo_saida:
            json.dump(
                resultado,
                arquivo_saida,
                ensure_ascii=False,
                indent=2,
            )

        print("\n=== RESULTADO ===")
        print("Arquivo:", destino)
        print("Recomendacao:", instrucao.recomendacao)
        print("Diarias:", instrucao.quantidade_diarias)
        print("Valor:", instrucao.valor_total)
        print("Verificacoes:", len(instrucao.verificacoes))
        print("Pendencias:", len(instrucao.pendencias))
        print("\nResultado registrado com auditoria.")

        return barreira["aprovado"]

    agente, pedido = criar_agente(
        numero,
        usar_memoria=False,
        chamadas_paralelas=False,
    )

    entrada = preparar_entrada(pedido)

    print("=" * 70)
    print("EXECUCAO AUDITADA - DESAFIO 01")
    print("=" * 70)
    print("Pedido:", numero)
    print("Modelo:", agente.model.id)
    print("Memoria: desativada")
    print("Paralelismo: desativado")
    print("Iniciando chamada real a OpenAI...")

    inicio = time.perf_counter()

    resposta = agente.run(
        entrada,
        session_id=numero,
        user_id=str(pedido["matricula"]),
    )

    duracao = time.perf_counter() - inicio

    print("\nStatus:", resposta.status)
    print("Duracao:", round(duracao, 2), "segundos")

    if resposta.status != RunStatus.completed:
        raise RuntimeError(
            "A execucao nao foi concluida. "
            "Nenhuma instrucao sera aprovada."
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
            "Formato de resposta nao reconhecido."
        )

    auditoria = registrar_ferramentas(resposta)

    imprimir_auditoria_ferramentas(auditoria)

    barreira = validar_instrucao(
        pedido,
        instrucao,
        auditoria,
    )

    print("\n=== BARREIRA INDEPENDENTE ===")
    print("Aprovado:", barreira["aprovado"])
    print("Mensagem:", barreira["mensagem"])

    for erro in barreira["erros"]:
        print("BLOQUEIO:", erro)

    metricas = None

    if resposta.metrics is not None:
        origem = resposta.metrics

        campos = (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "reasoning_tokens",
            "cost",
            "duration",
            "time_to_first_token",
        )

        metricas = {}

        for campo in campos:
            valor = getattr(origem, campo, None)

            if isinstance(valor, (int, float)) or valor is None:
                metricas[campo] = valor

        metricas = sanitizar_objeto(metricas)

    resultado = {
        "numero_pedido": numero,
        "modelo": agente.model.id,
        "duracao_segundos": round(duracao, 4),
        "status": str(resposta.status),
        "instrucao": sanitizar_objeto(
            instrucao.model_dump()
        ),
        "auditoria_ferramentas": auditoria,
        "barreira_validacao": barreira,
        "metricas": metricas,
        "aprovado_para_revisao_humana": barreira["aprovado"],
    }

    destino.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Modo exclusivo: impede sobrescrever resultados existentes.
    with destino.open("x", encoding="utf-8") as arquivo:
        json.dump(
            resultado,
            arquivo,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    print("\n=== RESULTADO ===")
    print("Arquivo:", destino)
    print("Recomendacao:", instrucao.recomendacao)
    print("Diarias:", instrucao.quantidade_diarias)
    print("Valor:", instrucao.valor_total)
    print("Verificacoes:", len(instrucao.verificacoes))

    if not barreira["aprovado"]:
        print(
            "ATENCAO: Instrucao bloqueada. "
            "Nao utilizar como parecer validado."
        )

    print("\nResultado registrado com auditoria.")

    return barreira["aprovado"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Executor auditado do Desafio 01."
    )

    parser.add_argument(
        "numero",
        help="Numero do pedido, por exemplo DIA-2026-0102",
    )

    args = parser.parse_args()

    try:
        aprovado = executar(args.numero)
    except Exception as erro:
        print("\nERRO NA EXECUCAO")
        print("Tipo:", type(erro).__name__)
        print(
            "Detalhes:",
            sanitizar_objeto(str(erro))[:500],
        )
        sys.exit(1)

    sys.exit(0 if aprovado else 2)
