"""Classifica falhas do SDK sem agente, rede ou credenciais reais."""

import json
import unittest
from unittest.mock import patch

import httpx
from openai import APIConnectionError, APITimeoutError, PermissionDeniedError

from experimento_memoria_complementacoes import MODELO, Medicao, _cliente_openai


class TransporteExperimentoOffline(unittest.TestCase):
    def conferir(self, responder, excecao, tipo, etapa, status=None, codigo=None):
        medicao = Medicao(None, None)
        medicao.atual.set({"finalidade": "memoria_pessoal"})
        tentativas = []

        def transporte(requisicao):
            tentativas.append(1)
            return responder(requisicao)

        with (
            patch("socket.socket.connect", side_effect=AssertionError("Rede proibida")),
            patch("socket.getaddrinfo", side_effect=AssertionError("DNS proibido")),
            httpx.Client(
                transport=httpx.MockTransport(transporte),
                event_hooks={"request": [medicao.antes_requisicao], "response": [medicao.depois_resposta]},
            ) as http,
        ):
            cliente = _cliente_openai(http, "chave-sintetica")
            with self.assertRaises(excecao):
                with medicao.observar_falha():
                    cliente.responses.create(model=MODELO, input="entrada offline")

        self.assertEqual(len(tentativas), 1)
        self.assertEqual(len(medicao.requisicoes), 1)
        self.assertTrue(medicao.interromper)
        falha, = medicao.falhas
        self.assertGreaterEqual(falha["segundos"], 0)
        self.assertEqual(falha, {
            "tipo": tipo, "etapa": etapa, "http_status": status, "codigo_provedor": codigo,
            "tentativas": 1, "segundos": falha["segundos"],
        })
        exportado = json.dumps(falha)
        for privado in ("marcador-privado", "chave-sintetica", "entrada offline"):
            self.assertNotIn(privado, exportado)

    def test_conexao_sem_retry(self):
        def falhar(requisicao):
            raise httpx.ConnectError("marcador-privado", request=requisicao)

        self.conferir(falhar, APIConnectionError, "ErroTransporte", "transporte")

    def test_timeout_sem_retry(self):
        def falhar(requisicao):
            raise httpx.ReadTimeout("marcador-privado", request=requisicao)

        self.conferir(falhar, APITimeoutError, "Timeout", "transporte")

    def test_http_403_sem_retry(self):
        for informado, permitido in (("marcador-privado", None), ("model_not_found", "model_not_found")):
            with self.subTest(permitido=permitido):
                def recusar(_requisicao):
                    return httpx.Response(403, json={"error": {
                        "message": "marcador-privado", "code": informado,
                    }})

                self.conferir(recusar, PermissionDeniedError, "ErroHTTP", "resposta_http", 403, permitido)


if __name__ == "__main__":
    unittest.main(verbosity=2)
