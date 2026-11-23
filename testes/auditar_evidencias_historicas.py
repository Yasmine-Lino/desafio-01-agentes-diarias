"""Confere a tabela de evidências históricas contra seus JSONs de origem.

O relatório contém apenas contagens, caminhos relativos e campos divergentes;
nenhum conteúdo de pedido, recomendação ou dado pessoal é impresso.
"""

from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TABELA = ROOT / "documentacao" / "EVIDENCIAS_COMPLEMENTARES.md"
ORIGENS = ROOT / "resultados" / "execucoes"
SAIDA_PADRAO = ROOT / "resultados" / "auditoria_entrega_final_20261122.json"
LOTE = ROOT / "resultados" / "lote_final_14_20261122T211104Z"


def primeiro_valor(registro: dict, caminhos: tuple[tuple[str, ...], ...]):
    for caminho in caminhos:
        valor = registro
        for chave in caminho:
            if not isinstance(valor, dict) or chave not in valor:
                valor = None
                break
            valor = valor[chave]
        if valor is not None:
            return valor
    return None


def _valor_origem(registro: dict, coluna: str):
    metricas = registro.get("metricas") or {}
    if coluna == "duration":
        return primeiro_valor(
            registro,
            (("duracao_segundos",), ("duracao_segundos_executor",),
             ("duracao_segundos_persistida",), ("metricas", "duration")),
        )
    if coluna in {"input", "output", "total", "cache_read", "cache_write"}:
        chave = {
            "input": "input_tokens",
            "output": "output_tokens",
            "total": "total_tokens",
            "cache_read": "cache_read_tokens",
            "cache_write": "cache_write_tokens",
        }[coluna]
        return metricas.get(chave)
    if coluna == "tools":
        return primeiro_valor(
            registro,
            (("auditoria_ferramentas", "total_chamadas"), ("auditoria", "total_chamadas")),
        )
    if coluna == "barrier":
        return primeiro_valor(
            registro,
            (("barreira_validacao", "aprovado"), ("validacao", "aprovado")),
        )
    if coluna == "recommendation":
        return primeiro_valor(registro, (("instrucao", "recomendacao"), ("recomendacao",)))
    raise ValueError(f"Coluna inesperada: {coluna}")


def _comparar(celula: str, valor, coluna: str) -> bool:
    if celula.strip().upper() == "N/D":
        return valor is None
    if coluna == "recommendation":
        return celula.strip().lower() == "sim" and bool(valor)
    if coluna == "barrier":
        esperado = celula.strip().lower() == "true"
        return isinstance(valor, bool) and valor is esperado
    try:
        exibido = float(celula.strip())
        origem = float(valor)
    except (TypeError, ValueError):
        return False
    tolerancia = 0.000051 if coluna == "duration" else 0.000001
    return abs(exibido - origem) <= tolerancia


def auditar() -> dict:
    linhas = TABELA.read_text(encoding="utf-8").splitlines()
    colunas = ("duration", "input", "output", "total", "cache_read", "cache_write",
               "tools", "barrier", "recommendation")
    divergencias = []
    ausentes = []
    nomes = []
    completos_tokens_cache = 0
    com_metricas_token = 0
    com_duracao = 0
    com_custo = 0
    com_recomendacao = 0
    com_auditoria_ferramentas = 0
    origem_duracao_executor = []
    diligencias_sem_modelo = 0
    execucoes_modelo_sem_tokens = []

    for linha in linhas:
        if not linha.startswith("| DIA-2026-"):
            continue
        celulas = [parte.strip() for parte in linha.strip("|").split("|")]
        nome = celulas[0]
        nomes.append(nome)
        caminho = ORIGENS / nome
        if not caminho.is_file():
            ausentes.append(nome)
            continue
        registro = json.loads(caminho.read_text(encoding="utf-8"))
        metricas = registro.get("metricas") or {}
        diligencia_local = (
            registro.get("tipo_execucao") == "diligencia_preliminar"
            or registro.get("status") == "diligencia_preliminar_concluida"
        )
        diligencias_sem_modelo += int(diligencia_local)
        if all(metricas.get(k) is not None for k in
               ("input_tokens", "output_tokens", "total_tokens", "cache_read_tokens", "cache_write_tokens")):
            completos_tokens_cache += 1
        if all(metricas.get(k) is not None for k in ("input_tokens", "output_tokens", "total_tokens")):
            com_metricas_token += 1
        elif not diligencia_local and registro.get("tipo_execucao", "").startswith("complementacao"):
            execucoes_modelo_sem_tokens.append(nome)
        if _valor_origem(registro, "duration") is not None:
            com_duracao += 1
        if metricas.get("cost") is not None or registro.get("custo_estimado_usd") is not None:
            com_custo += 1
        if _valor_origem(registro, "recommendation") is not None:
            com_recomendacao += 1
        auditoria = registro.get("auditoria_ferramentas") or registro.get("auditoria") or {}
        if auditoria.get("total_chamadas"):
            com_auditoria_ferramentas += 1
        if "duracao_segundos_executor" in registro:
            origem_duracao_executor.append(nome)

        valores = [_valor_origem(registro, coluna) for coluna in colunas]
        for indice, coluna in enumerate(colunas, start=1):
            if indice >= len(celulas):
                divergencias.append({"arquivo": nome, "campo": coluna})
                continue
            exibido = celulas[indice].strip().upper()
            colunas_tokens = {"input", "output", "total", "cache_read", "cache_write"}
            if exibido == "N/A":
                if not diligencia_local or coluna not in colunas_tokens or valores[indice - 1] is not None:
                    divergencias.append({"arquivo": nome, "campo": coluna})
                continue
            if not _comparar(celulas[indice], valores[indice - 1], coluna):
                divergencias.append({"arquivo": nome, "campo": coluna})

    return {
        "linhas_tabela": len(nomes),
        "arquivos_origem_encontrados": len(nomes) - len(ausentes),
        "campos_por_linha": list(colunas),
        "divergencias": divergencias,
        "arquivos_origem_ausentes": ausentes,
        "metricas_tokens_disponiveis": com_metricas_token,
        "tokens_e_cache_completos": completos_tokens_cache,
        "tokens_nao_aplicaveis_diligencias_locais": diligencias_sem_modelo,
        "execucoes_de_complementacao_sem_tokens": execucoes_modelo_sem_tokens,
        "duracoes_disponiveis": com_duracao,
        "custos_historicos_disponiveis": com_custo,
        "recomendacoes_preservadas": com_recomendacao,
        "trilhas_de_ferramentas_na_origem": com_auditoria_ferramentas,
        "duracao_com_campo_executor": origem_duracao_executor,
        "status": "conferido" if not divergencias and not ausentes and len(nomes) == 34 else "divergencias",
    }


def auditar_lote_final() -> dict:
    manifesto = json.loads((LOTE / "manifesto.json").read_text(encoding="utf-8"))
    arquivos = sorted(p for p in LOTE.glob("*.json") if p.name != "manifesto.json")
    registros = [json.loads(p.read_text(encoding="utf-8")) for p in arquivos]
    chamadas = [r for r in registros if r.get("modelo_invocado") is True]
    locais = [r for r in registros if r.get("modelo_invocado") is False]
    soma = {
        campo: sum(int(r.get(campo) or 0) for r in registros)
        for campo in ("input_tokens", "output_tokens", "total_tokens")
    }
    soma_duracao_casos = round(sum(float(r.get("duracao_segundos") or 0) for r in registros), 6)
    custo_casos = sum((Decimal(str(r["custo_estimado_usd"])) for r in registros
                       if r.get("custo_estimado_usd") is not None), Decimal("0"))
    metricas = manifesto.get("metricas") or {}
    complementacoes = [r for r in registros if r.get("etapa") == "complementacao"]
    checks = {
        "14_registros": len(registros) == 14,
        "manifesto_14_de_14": metricas.get("casos_concluidos") == 14 and metricas.get("casos_esperados") == 14,
        "status_conferida": all(r.get("status") == "conferida" for r in registros),
        "barreira_aprovada": all(r.get("barreira") == "aprovada" for r in registros),
        "revisao_humana_obrigatoria": all(r.get("revisao_humana_obrigatoria") is True for r in registros),
        "12_chamadas_modelo": len(chamadas) == 12 and metricas.get("chamadas_logicas_ao_modelo") == 12,
        "2_diligencias_locais": len(locais) == 2 and all(r.get("etapa") == "diligencia_local" for r in locais),
        "tokens_manifesto": all(soma[k] == metricas.get(k) for k in soma),
        "custo_soma_manifesto": custo_casos == Decimal(str(metricas.get("custo_estimado_usd"))),
        "complementacoes_mesma_sessao_e_titular": len(complementacoes) == 2 and all(
            r.get("correcao_validada") is True
            and r.get("sessao_original_preservada") is True
            and r.get("titular_corrigido_utilizado") is True
            for r in complementacoes
        ),
    }
    cache_rows = sum(any(k in r for k in ("cache_read_tokens", "cache_write_tokens")) for r in registros)
    recommendation_rows = sum("recomendacao" in r for r in registros)
    audit_rows = sum(any(k in r for k in ("auditoria", "auditoria_ferramentas")) for r in registros)
    detailed_barrier_rows = sum(any(k in r for k in ("validacao", "barreira_validacao")) for r in registros)
    return {
        "arquivos_de_caso": len(registros),
        "status_conferida": sum(r.get("status") == "conferida" for r in registros),
        "revisao_humana_obrigatoria": sum(r.get("revisao_humana_obrigatoria") is True for r in registros),
        "chamadas_logicas_modelo": len(chamadas),
        "diligencias_locais_sem_modelo": len(locais),
        "complementacoes_corrigidas": len(complementacoes),
        "barreiras_aprovadas": sum(r.get("barreira") == "aprovada" for r in registros),
        "soma_tokens_por_caso": soma,
        "tokens_manifesto": {k: metricas.get(k) for k in soma},
        "soma_duracao_registros_segundos": soma_duracao_casos,
        "duracao_total_manifesto_segundos": metricas.get("duracao_total_segundos"),
        "diferenca_nao_atribuida_por_registro_segundos": round(
            float(metricas.get("duracao_total_segundos") or 0) - soma_duracao_casos, 6
        ),
        "soma_custo_estimado_usd": str(custo_casos),
        "custo_estimado_manifesto_usd": metricas.get("custo_estimado_usd"),
        "custo_faturado": metricas.get("custo_faturado_usd"),
        "linhas_com_contadores_cache": cache_rows,
        "linhas_com_recomendacao": recommendation_rows,
        "linhas_com_trilha_ferramentas": audit_rows,
        "linhas_com_detalhes_barreira": detailed_barrier_rows,
        "checks": checks,
        "status": "conferido" if all(checks.values()) else "divergencias",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO,
                        help="Arquivo JSON para o resumo sanitizado da auditoria.")
    args = parser.parse_args()
    relatorio = auditar()
    relatorio["lote_final"] = auditar_lote_final()
    if relatorio["lote_final"]["status"] != "conferido":
        relatorio["status"] = "divergencias"
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(relatorio, ensure_ascii=False, indent=2))
    return 0 if relatorio["status"] == "conferido" else 1


if __name__ == "__main__":
    raise SystemExit(main())
