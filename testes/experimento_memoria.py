"""Experimento comparativo de memoria do agente de diarias."""

import argparse
import json
import sys
import time
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parents[1]
if str(RAIZ_PROJETO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROJETO))

from agno.run.agent import RunStatus

from agente import criar_agente, preparar_entrada
from auditoria_execucao import registrar_ferramentas, sanitizar_objeto
from barreira_validacao import validar_instrucao
from modelos import Instrucao


BASE = Path(__file__).resolve().parents[1]
PASTA = BASE / "resultados" / "experimentos_memoria"
SAIDAS = PASTA / "comparacoes"

CENARIOS = {
    "A": {
        "usar_memoria": False,
        "memoria_usuario": False,
        "banco": None,
    },
    "B": {
        "usar_memoria": True,
        "memoria_usuario": False,
        "banco": PASTA / "cenario_B.db",
    },
    "C": {
        "usar_memoria": True,
        "memoria_usuario": True,
        "banco": PASTA / "cenario_C.db",
    },
}


def extrair_metricas(resposta):
    """Registra somente metricas disponibilizadas pelo Agno."""
    metricas = resposta.metrics

    if metricas is None:
        return {}

    campos = (
        "duration",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "reasoning_tokens",
        "cost",
    )

    return {
        campo: getattr(metricas, campo, None)
        for campo in campos
    }


def executar(cenario, numero, turno=1):
    """Executa um pedido e registra evidencias auditaveis."""
    configuracao = CENARIOS[cenario]

    destino = SAIDAS / f"{cenario}_{numero}_turno_{turno:02d}.json"

    if destino.exists():
        raise FileExistsError(
            f"Resultado existente; sobrescrita proibida: {destino}"
        )

    agente, pedido = criar_agente(
        numero,
        usar_memoria=configuracao["usar_memoria"],
        memoria_usuario=configuracao["memoria_usuario"],
        caminho_banco=configuracao["banco"],
        chamadas_paralelas=False,
    )

    entrada = preparar_entrada(pedido)

    inicio = time.perf_counter()
    resposta = agente.run(entrada)
    duracao = time.perf_counter() - inicio

    status = getattr(resposta.status, "value", str(resposta.status))
    concluido = resposta.status == RunStatus.completed

    instrucao = resposta.content

    if concluido and isinstance(instrucao, Instrucao):
        auditoria = registrar_ferramentas(resposta)
        validacao = validar_instrucao(
            pedido,
            instrucao,
            auditoria,
        )
        conteudo = instrucao.model_dump(mode="json")
    else:
        auditoria = registrar_ferramentas(resposta)
        validacao = {
            "aprovado": False,
            "erros": [
                "Execucao incompleta ou resposta fora do schema."
            ],
        }
        conteudo = None

    resultado = {
        "cenario": cenario,
        "numero_pedido": numero,
        "status": status,
        "duracao_segundos": duracao,
        "metricas": extrair_metricas(resposta),
        "instrucao": conteudo,
        "auditoria": auditoria,
        "validacao": validacao,
        "aprovado_para_revisao_humana": validacao["aprovado"],
    }

    resultado = sanitizar_objeto(resultado)

    with destino.open("x", encoding="utf-8") as arquivo:
        json.dump(
            resultado,
            arquivo,
            ensure_ascii=False,
            indent=2,
        )

    print("=" * 70)
    print("EXPERIMENTO DE MEMORIA")
    print("=" * 70)
    print("Cenario:", cenario)
    print("Pedido:", numero)
    print("Status:", status)
    print("Duracao:", round(duracao, 3), "segundos")
    print("Ferramentas:", auditoria["total_chamadas"])
    print("Barreira aprovada:", validacao["aprovado"])
    print("Resultado:", destino)

    return resultado


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cenario",
        choices=sorted(CENARIOS),
        required=True,
    )
    parser.add_argument(
        "--pedido",
        required=True,
    )
    parser.add_argument(
        "--turno",
        type=int,
        default=1,
    )
    argumentos = parser.parse_args()

    if argumentos.turno < 1:
        parser.error("--turno deve ser maior ou igual a 1")

    executar(
        argumentos.cenario,
        argumentos.pedido,
        argumentos.turno,
    )


if __name__ == "__main__":
    main()
