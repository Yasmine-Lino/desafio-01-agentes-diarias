"""Valida as seis combinações com o adaptador real e transporte HTTP simulado."""

import json
import socket
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import httpx

from experimento_memoria_complementacoes import MODOS, MODELO, PEDIDOS, Medicao, _suspensao, executar_combinacao


class ExperimentoMemoriaOffline(unittest.TestCase):
    def setUp(self):
        recursos = self.enterContext(ExitStack())
        recursos.enter_context(patch("dotenv.load_dotenv", return_value=False))
        acessos = []

        def negar(*args, **kwargs):
            acessos.append(True)
            raise AssertionError("Acesso externo bloqueado.")

        recursos.callback(lambda: self.assertFalse(acessos, "Houve tentativa de rede externa."))
        for nome in ("connect", "connect_ex", "send", "sendall", "sendto"):
            recursos.enter_context(patch.object(socket.socket, nome, negar))
        for nome in ("getaddrinfo", "gethostbyname", "gethostbyname_ex", "create_connection"):
            recursos.enter_context(patch.object(socket, nome, negar))

    def transporte(self, pedido, *, ids_opacos=False):
        from barreira_validacao import _encaminhamento, _produzir_instrucao
        from validacao_normativa import obter_evidencias_normativas

        evidencias = obter_evidencias_normativas(pedido)
        resultado = _produzir_instrucao(pedido, evidencias, _encaminhamento(pedido, evidencias))
        ferramentas = ["verificar_cadastro", "verificar_prestacoes", "verificar_calculo", "verificar_orcamento"]

        def responder(requisicao):
            corpo = json.loads(requisicao.content)
            self.assertEqual(corpo["model"], MODELO)
            principal = any(t.get("name") == "verificar_cadastro" for t in corpo.get("tools") or ())
            passo = sum(item.get("type") == "function_call_output" for item in corpo["input"])
            if principal and passo < len(ferramentas):
                id_base = f"abcdef{passo}a12345678901bcdefabcdef" if ids_opacos else f"offline_{passo}"
                saida = {
                    "type": "function_call", "id": f"fc_{id_base}", "call_id": f"call_{id_base}",
                    "name": ferramentas[passo], "arguments": "{}", "status": "completed",
                }
            else:
                saida = {
                    "type": "message", "id": f"msg_offline_{passo}", "role": "assistant", "status": "completed",
                    "content": [{"type": "output_text", "text": resultado.model_dump_json() if principal else
                                 "Nenhuma memória nova no transporte simulado.", "annotations": []}],
                }
            return httpx.Response(200, json={
                "id": f"resp_offline_{passo}", "object": "response", "created_at": 0, "model": MODELO,
                "status": "completed", "output": [saida], "error": None,
                "usage": {"input_tokens": 80, "output_tokens": 20, "total_tokens": 100,
                          "input_tokens_details": {"cached_tokens": 0},
                          "output_tokens_details": {"reasoning_tokens": 0}},
            })

        return httpx.MockTransport(responder)

    def test_cenario_b_com_ids_opacos_das_ferramentas(self):
        from complementacoes import aplicar_complementacao

        for numero in PEDIDOS:
            with self.subTest(numero=numero):
                corrigido = aplicar_complementacao(numero)["pedido_corrigido"]
                registro = executar_combinacao(
                    numero, "B", "chave-sintetica-sem-rede", transporte=self.transporte(corrigido, ids_opacos=True),
                )
                local, retomada = registro["turnos"]
                self.assertEqual(retomada["status"], "conferido", retomada["falhas_no_modelo"])
                self.assertEqual(local["session_id"], retomada["session_id"])
                self.assertEqual(retomada["session_id"], numero)
                self.assertEqual(retomada["user_id"], corrigido["matricula"])
                correcao = retomada["correcao_recuperada"]
                self.assertEqual(correcao["valor_validado"], corrigido[correcao["campo"]])
                self.assertEqual(registro["configuracao"]["limite_runs"], 3)
                self.assertEqual(retomada["runs_persistidos"], 1)
                self.assertEqual(retomada["chamadas_por_finalidade"], {"analise": 5})
                self.assertEqual(retomada["barreira"], "aprovada")
                self.assertTrue(all(c["payload_verificado"] for c in retomada["contexto"]))
                self.assertTrue(all(not c["mensagens_de_replay"] for c in retomada["contexto"]))
                self.assertNotIn("12345678901", json.dumps(registro))

    def test_privacidade_preserva_bloqueio_em_conteudo_e_ids_fora_do_formato(self):
        for item in (
            {"type": "function_call", "call_id": "call_abc12345678901xyz", "arguments": '{"cpf":"12345678901"}'},
            {"type": "function_call_output", "call_id": "call_abc12345678901xyz", "output": "conta 001-2"},
            {"type": "message", "role": "user", "content": "agência 0001"},
            {"type": "function_call", "call_id": "call_123.456.789-01", "arguments": "{}"},
        ):
            with self.subTest(tipo=item["type"]):
                medicao = Medicao(None, None)
                medicao.atual.set({"finalidade": "memoria_pessoal"})
                requisicao = httpx.Request("POST", "https://api.openai.com/v1/responses", json={
                    "model": MODELO, "input": [item],
                })
                with self.assertRaisesRegex(ValueError, "dados_sensiveis_detectados"):
                    medicao.antes_requisicao(requisicao)
                self.assertEqual(medicao.requisicoes, [])

    def test_seis_combinacoes_e_separacao_do_contexto(self):
        from complementacoes import aplicar_complementacao

        for numero in PEDIDOS:
            complemento = aplicar_complementacao(numero)
            corrigido = complemento["pedido_corrigido"]
            for modo in MODOS:
                with self.subTest(numero=numero, modo=modo):
                    registro = executar_combinacao(
                        numero, modo, "chave-sintetica-sem-rede", transporte=self.transporte(corrigido),
                    )
                    local, retomada = registro["turnos"]
                    self.assertEqual((local["status"], retomada["status"]), ("conferido", "conferido"), registro)
                    self.assertEqual(local["chamadas_ao_modelo"], 0)
                    self.assertIsNone(local["input_tokens"])
                    self.assertIsNone(local["user_id"])
                    self.assertEqual(local["session_id"], retomada["session_id"])
                    self.assertEqual(retomada["session_id"], numero)
                    self.assertTrue(retomada["user_id"] == corrigido["matricula"])
                    self.assertEqual(retomada["barreira"], "aprovada")
                    self.assertEqual(len(retomada["verificacoes"]), 6)
                    self.assertEqual(retomada["runs_persistidos"], 0 if modo == "A" else 1)
                    esperado = {"analise": 5}
                    if modo == "C":
                        esperado["memoria_pessoal"] = 1
                    self.assertEqual(retomada["chamadas_por_finalidade"], esperado)
                    self.assertEqual(retomada["input_tokens"], 80 * sum(esperado.values()))
                    self.assertIsNotNone(retomada["custo_estimado_usd"])
                    for captura in retomada["contexto"]:
                        self.assertEqual(captura["mensagens_de_replay"], 0)
                        self.assertFalse(captura["memoria_pessoal_no_sistema"])
                        self.assertTrue(captura["payload_verificado"])
                        if captura["finalidade"] == "analise":
                            self.assertFalse(captura["justificativa_presente"])
                    # A exportação omite nome, justificativa e matrícula originalmente divergente.
                    exportado = json.dumps(registro, ensure_ascii=False)
                    self.assertFalse(corrigido["nome"] in exportado)
                    if numero.endswith("0112"):
                        self.assertFalse(complemento["pedido_original"]["matricula"] in exportado)

    def test_http_403_interrompe_sem_repetir(self):
        def bloquear(_requisicao):
            return httpx.Response(403, json={"error": {"message": "marcador de erro não publicável"}})

        registro = executar_combinacao(
            PEDIDOS[0], "A", "chave-sintetica-sem-rede", transporte=httpx.MockTransport(bloquear),
        )
        turno = registro["turnos"][1]
        self.assertEqual(turno["status"], "erro")
        self.assertEqual(turno["chamadas_ao_modelo"], 1)
        self.assertIsNone(turno["input_tokens"])
        self.assertIsNone(turno["custo_estimado_usd"])
        self.assertEqual(_suspensao(registro), "http_403")
        self.assertFalse("marcador de erro" in json.dumps(registro))


if __name__ == "__main__":
    unittest.main(verbosity=2)
