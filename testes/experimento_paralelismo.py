import argparse
import json
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from agno.run.agent import RunStatus

from agente import criar_agente, preparar_entrada
from auditoria_execucao import registrar_ferramentas, sanitizar_objeto
from barreira_validacao import validar_instrucao
from modelos import Instrucao


NUMERO = "DIA-2026-0101"
SAIDAS = BASE / "resultados" / "experimento_paralelismo"


def extrair_metricas(resposta):
    metricas = getattr(resposta, "metrics", None)

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
        "time_to_first_token",
    )

    return {
        campo: valor
        for campo in campos
        if (
            (valor := getattr(metricas, campo, None)) is None
            or isinstance(valor, (int, float))
        )
    }


def executar(modo):
    paralelo = modo == "paralelo"
    destino = SAIDAS / f"{NUMERO}_{modo}.json"

    if destino.exists():
        raise FileExistsError(
            "Resultado ja existente. Sobrescrita proibida: "
            + str(destino)
        )

    agente, pedido = criar_agente(
        NUMERO,
        usar_memoria=False,
        chamadas_paralelas=paralelo,
    )

    if agente.model.parallel_tool_calls is not paralelo:
        raise RuntimeError(
            "Configuracao de paralelismo inconsistente."
        )

    entrada = preparar_entrada(pedido)

    print("=" * 72)
    print("EXPERIMENTO - FERRAMENTAS SEQUENCIAIS X PARALELAS")
    print("=" * 72)
    print("Pedido:", NUMERO)
    print("Modo:", modo)
    print("Modelo:", agente.model.id)
    print("Memoria: desativada")
    print("Paralelismo habilitado:", paralelo)
    print("Iniciando chamada real a OpenAI...")

    inicio = time.perf_counter()

    resposta = agente.run(
        entrada,
        session_id=NUMERO,
        user_id=str(pedido["matricula"]),
    )

    duracao = time.perf_counter() - inicio

    print("\nStatus:", resposta.status)
    print("Duracao:", round(duracao, 3), "segundos")

    if resposta.status != RunStatus.completed:
        raise RuntimeError(
            "Execucao incompleta. Resultado nao aprovado."
        )

    conteudo = resposta.content

    if isinstance(conteudo, Instrucao):
        instrucao = conteudo
    elif isinstance(conteudo, dict):
        instrucao = Instrucao.model_validate(conteudo)
    elif isinstance(conteudo, str):
        instrucao = Instrucao.model_validate_json(conteudo)
    else:
        raise TypeError("Resposta fora do schema esperado.")

    auditoria = registrar_ferramentas(resposta)

    validacao = validar_instrucao(
        pedido,
        instrucao,
        auditoria,
    )

    print("\nRESULTADO")
    print("Recomendacao:", instrucao.recomendacao)
    print("Quantidade:", instrucao.quantidade_diarias)
    print("Valor:", instrucao.valor_total)
    print("Ferramentas:", auditoria.get("total_chamadas"))
    print("Nomes:", auditoria.get("nomes_ferramentas"))
    print("Barreira aprovada:", validacao.get("aprovado"))
    print("Erros:", validacao.get("erros"))

    if not validacao.get("aprovado"):
        raise RuntimeError(
            "Barreira normativa reprovada. "
            "Nenhum resultado sera aprovado."
        )

    if auditoria.get("total_chamadas") != 4:
        raise RuntimeError(
            "Quantidade inesperada de ferramentas."
        )

    if any(
        chamada.get("erro")
        for chamada in auditoria.get("chamadas", [])
    ):
        raise RuntimeError("Ferramenta com erro.")

    metricas = extrair_metricas(resposta)

    registro = {
        "experimento": "sequencial_versus_paralelo",
        "numero_pedido": NUMERO,
        "modo": modo,
        "modelo": agente.model.id,
        "parallel_tool_calls": paralelo,
        "memoria_ativada": False,
        "status": str(resposta.status),
        "duracao_segundos": round(duracao, 6),
        "instrucao": instrucao.model_dump(mode="json"),
        "auditoria": auditoria,
        "validacao": validacao,
        "metricas": metricas,
        "aprovado_para_revisao_humana": True,
        "observacao": (
            "Paralelismo habilitado nao comprova, por si so, "
            "execucao simultanea das ferramentas."
        ),
    }

    SAIDAS.mkdir(parents=True, exist_ok=True)

    with destino.open("x", encoding="utf-8") as arquivo:
        json.dump(
            sanitizar_objeto(registro),
            arquivo,
            ensure_ascii=False,
            indent=2,
            default=str,
        )

    print("\nMETRICAS")
    print("Tempo:", round(duracao, 3), "segundos")
    print("Tokens de entrada:", metricas.get("input_tokens"))
    print("Tokens de saida:", metricas.get("output_tokens"))
    print("Tokens totais:", metricas.get("total_tokens"))
    print("Custo informado:", metricas.get("cost"))

    print("\nResultado salvo:", destino)
    print("Execucao concluida. Aguardando auditoria.")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--modo",
        choices=("sequencial", "paralelo"),
        required=True,
    )

    argumentos = parser.parse_args()
    executar(argumentos.modo)


if __name__ == "__main__":
    main()
