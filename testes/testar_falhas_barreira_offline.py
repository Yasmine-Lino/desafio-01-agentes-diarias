"""Quatro falhas sint?ticas bloqueadas pela barreira, sem rede ou banco."""

import unittest
from copy import deepcopy
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modelos import Instrucao, Verificacao
from barreira_validacao import CONSULTAS_AGNO, validar_instrucao


RUN_ID = "12345678-1234-1234-1234-123456789abc"
PEDIDO = {
    "numero": "DIA-2099-0001", "matricula": "000001", "nome": "Titular Sint?tico",
    "destino_municipio": "Cidade Teste", "destino_uf": "MT",
    "data_pedido": "2099-01-01", "data_partida": "2099-01-20",
    "data_retorno": "2099-01-21", "justificativa": "Viagem sint?tica.",
}
ARGUMENTOS = {
    "consultar_servidor": {"matricula": "000001"},
    "consultar_historico": {"matricula": "000001", "mes_referencia": "2099-01", "data_analise": "2099-01-01"},
    "calcular_diarias": {"matricula": "000001", "mes_referencia": "2099-01", "data_analise": "2099-01-01",
                          "destino_uf": "MT", "data_pedido": "2099-01-01", "data_partida": "2099-01-20",
                          "data_retorno": "2099-01-21"},
    "consultar_saldo": {"matricula": "000001", "valor_solicitado": 220.0},
}
RESULTADOS = {
    "consultar_servidor": {"matricula": "000001", "nome": "Titular Sint?tico", "grupo_diaria": "C", "unidade": "TST"},
    "consultar_historico": {"mes_referencia": "2099-01", "possui_prestacao_vencida": False, "total_diarias_mes": 0},
    "calcular_diarias": {"quantidade_diarias": 1.0, "valor_total": 220.0, "antecedencia_atendida": True,
                          "total_projetado_mes": 1.0, "limite_mensal": 10},
    "consultar_saldo": {"unidade": "TST", "saldo_disponivel": 1000.0, "valor_solicitado": 220.0,
                         "saldo_suficiente": True},
}
CONTEXTO = {
    "run_id": RUN_ID, "numero": PEDIDO["numero"], "matricula": PEDIDO["matricula"],
    "data_pedido": PEDIDO["data_pedido"], "data_partida": PEDIDO["data_partida"],
    "data_retorno": PEDIDO["data_retorno"], "destino_uf": PEDIDO["destino_uf"],
}
EVIDENCIAS = {
    "contexto": CONTEXTO, "argumentos": ARGUMENTOS, "resultados": RESULTADOS,
    "analise_merito_permitida": True, "situacoes": {
        "cadastro": "atende", "dados_completos": "atende", "antecedencia": "atende",
        "prestacao_contas": "atende", "limite_mensal": "atende", "saldo_orcamentario": "atende",
    },
    "pendencias": [], "antecedencia_minima_dias": 10,
}
AUDITORIA = {
    "estado_contexto": "completo", "contexto_execucao": CONTEXTO,
    "estado_trilha": "completa", "nomes_ferramentas": list(CONSULTAS_AGNO),
    "total_chamadas": 4, "chamadas": [], "chamadas_python": [],
}
for indice, (nome, consulta) in enumerate(CONSULTAS_AGNO.items()):
    id_chamada = f"call_sintetica_{indice}"
    AUDITORIA["chamadas"].append({
        "nome": nome, "tool_call_id": id_chamada, "erro": False,
        "argumentos": deepcopy(ARGUMENTOS[consulta]), "resultado": deepcopy(RESULTADOS[consulta]),
    })
    AUDITORIA["chamadas_python"].append({
        "ferramenta_agno": nome, "nome": consulta, "inicio_chamada": consulta != "consultar_saldo",
        "executada": True, "erro": False, "estados_argumentos": {k: "presente" for k in ARGUMENTOS[consulta]},
        "argumentos": deepcopy(ARGUMENTOS[consulta]), "resultado": deepcopy(RESULTADOS[consulta]),
    })
AUDITORIA["chamadas_python"].append({
    "ferramenta_agno": "verificar_orcamento", "nome": "calcular_diarias", "inicio_chamada": True,
    "executada": True, "erro": False, "estados_argumentos": {k: "presente" for k in ARGUMENTOS["calcular_diarias"]},
    "argumentos": deepcopy(ARGUMENTOS["calcular_diarias"]), "resultado": deepcopy(RESULTADOS["calcular_diarias"]),
})


def instrucao():
    criterios = ("cadastro", "dados_completos", "antecedencia", "prestacao_contas", "limite_mensal", "saldo_orcamentario")
    return Instrucao(
        numero_pedido=PEDIDO["numero"], matricula=PEDIDO["matricula"], quantidade_diarias=1.0, valor_total=220.0,
        verificacoes=[Verificacao(criterio=c, situacao="atende", detalhe="Evid?ncia sint?tica.") for c in criterios],
        recomendacao="apto_para_autorizacao", exige_autorizacao_superior=False, pendencias=[], alertas=[],
        minuta_despacho="Minuta sint?tica para revis?o humana.",
    )


class FalhasBarreiraOffline(unittest.TestCase):
    def validar(self, dados_auditoria, dados_instrucao):
        with patch("barreira_validacao.validar_pedido", return_value={"pode_analisar_merito": True}), \
             patch("barreira_validacao.obter_evidencias_normativas", return_value=deepcopy(EVIDENCIAS)), \
             patch("barreira_validacao.conferir_verificacoes", return_value={"divergencias": []}):
            return validar_instrucao(PEDIDO, dados_instrucao, dados_auditoria)

    def assert_bloqueada(self, parecer):
        self.assertFalse(parecer["aprovado"])
        self.assertIsNone(parecer["instrucao_conferida"])
        self.assertEqual(parecer["mensagem"], "Instrucao bloqueada para analise manual.")

    def test_erro_em_ferramenta_obrigatoria(self):
        auditoria = deepcopy(AUDITORIA)
        chamada = next(x for x in auditoria["chamadas"] if x["nome"] == "verificar_calculo")
        chamada["erro"] = True
        self.assert_bloqueada(self.validar(auditoria, instrucao()))

    def test_ferramenta_obrigatoria_ausente(self):
        auditoria = deepcopy(AUDITORIA)
        auditoria["chamadas"] = [x for x in auditoria["chamadas"] if x["nome"] != "verificar_calculo"]
        auditoria["nomes_ferramentas"].remove("verificar_calculo")
        auditoria["total_chamadas"] = 3
        self.assert_bloqueada(self.validar(auditoria, instrucao()))

    def test_valor_financeiro_adulterado(self):
        adulterada = instrucao().model_copy(update={"valor_total": 221.0})
        self.assert_bloqueada(self.validar(deepcopy(AUDITORIA), adulterada))

    def test_quantidade_diarias_adulterada(self):
        adulterada = instrucao().model_copy(update={"quantidade_diarias": 1.5})
        self.assert_bloqueada(self.validar(deepcopy(AUDITORIA), adulterada))


if __name__ == "__main__":
    unittest.main(verbosity=2)
