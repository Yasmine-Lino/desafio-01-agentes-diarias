"""Testes offline do orquestrador final; todos os executores sao simulados."""

import json
import sys
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "testes"))

import executar_lote_final as lote


class ExecutorLoteFinalOffline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.saida = Path(self.tmp.name) / "lote"

    @staticmethod
    def resultado(*, status="conferida", tipo="analise_merito", metricas=None, duracao=0.25):
        return {
            "status": status,
            "tipo_execucao": tipo,
            "metricas": metricas,
            "duracao_segundos": duracao,
        }

    def test_sequencia_14_casos_e_complementacoes_sem_modelo(self):
        pedidos = []
        complementos = []

        def pedido(protocolo):
            pedidos.append(protocolo)
            return self.resultado(metricas={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12})

        def complemento(protocolo, registrar_local):
            complementos.append(protocolo)
            registrar_local(self.resultado(
                tipo="diligencia_preliminar", metricas=None, duracao=0.01,
            ))
            self.assertEqual(protocolo, "DIA-2026-0111" if len(complementos) == 1 else "DIA-2026-0112")
            return self.resultado(metricas={"input_tokens": 20, "output_tokens": 3, "total_tokens": 23})

        manifesto = lote.executar_lote(pedido, complemento, diretorio_saida=self.saida)
        self.assertEqual(pedidos, list(lote.PEDIDOS_COMUNS))
        self.assertEqual(complementos, list(lote.PEDIDOS_COMPLEMENTADOS))
        self.assertEqual(manifesto["estado"], "concluido")
        self.assertEqual(manifesto["casos"], list(lote.CASOS_ESPERADOS))
        self.assertEqual(manifesto["metricas"]["casos_concluidos"], 14)
        self.assertEqual(manifesto["metricas"]["chamadas_logicas_ao_modelo"], 12)
        self.assertTrue((self.saida / "manifesto.json").is_file())

    def test_diligencia_persistida_antes_de_falha_na_complementacao(self):
        chamadas = []

        def pedido(protocolo):
            chamadas.append(protocolo)
            return self.resultado(metricas={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})

        def complemento(protocolo, registrar_local):
            registrar_local(self.resultado(tipo="diligencia_preliminar", metricas=None))
            raise TimeoutError("texto simulado nao deve ser salvo")

        manifesto = lote.executar_lote(pedido, complemento, diretorio_saida=self.saida)
        self.assertEqual(manifesto["estado"], "interrompido")
        self.assertEqual(len(chamadas), 10)
        self.assertTrue((self.saida / "11_DIA-2026-0111_diligencia_local.json").exists())
        self.assertTrue((self.saida / "12_DIA-2026-0111_complementacao.json").exists())
        falha = json.loads((self.saida / "12_DIA-2026-0111_complementacao.json").read_text(encoding="utf-8"))
        self.assertEqual(falha["classe_erro"], "TimeoutError")
        self.assertNotIn("texto simulado", (self.saida / "manifesto.json").read_text(encoding="utf-8"))

    def test_metricas_ausentes_nao_sao_inventadas_e_custo_faturado_e_null(self):
        api = lote._projetar_caso(
            "DIA-2026-0101", "DIA-2026-0101", "analise",
            self.resultado(metricas=None),
        )
        local = lote._projetar_caso(
            "DIA-2026-0111/diligencia_local", "DIA-2026-0111", "diligencia_local",
            self.resultado(tipo="diligencia_preliminar", metricas=None),
        )
        self.assertIsNone(api["input_tokens"])
        self.assertIsNone(api["output_tokens"])
        self.assertIsNone(api["total_tokens"])
        self.assertIsNone(api["custo_estimado_usd"])
        self.assertIsNone(api["custo_faturado_usd"])
        self.assertEqual((local["input_tokens"], local["output_tokens"], local["total_tokens"]), (0, 0, 0))
        self.assertEqual(local["custo_estimado_usd"], "0E-8")

    def test_consolidacao_custo_estimado_com_tarifa_declarada(self):
        custo = lote.estimar_custo({"input_tokens": 1000, "output_tokens": 100})
        self.assertEqual(custo, lote.Decimal("0.00032"))
        registros = [lote._projetar_caso(
            "DIA-2026-0101", "DIA-2026-0101", "analise",
            self.resultado(metricas={"input_tokens": 1000, "output_tokens": 100, "total_tokens": 1100}),
        )]
        consolidado = lote.consolidar(registros, concluido=False, duracao_total=1.5)
        self.assertEqual(consolidado["input_tokens"], 1000)
        self.assertEqual(consolidado["total_tokens"], 1100)
        self.assertIsNone(consolidado["custo_faturado_usd"])

    def test_adaptador_complemento_retomada_na_sessao_e_titular_corrigidos(self):
        class BarreiraFalsa:
            def __init__(self, segredo):
                self.segredo = segredo

            def preparar(self, **kwargs):
                self.preparado = kwargs

            def vincular_protocolo_validado(self, protocolo, titular, **kwargs):
                self.vinculo = (protocolo, titular)

            @contextmanager
            def abrir_agno(self, titular, **kwargs):
                yield object()

        for protocolo, titular, campo, original_valor, corrigido_valor in (
            ("DIA-2026-0111", "123456", "data_retorno", None, "2026-11-20"),
            ("DIA-2026-0112", "234567", "matricula", "345678", "234567"),
        ):
            with self.subTest(protocolo=protocolo):
                original = {"numero": protocolo, "matricula": titular, campo: original_valor}
                corrigido = {**original, campo: corrigido_valor}
                preparado = {"pedido_corrigido": corrigido, "session_id": protocolo, "user_id": titular}
                local = self.resultado(tipo="diligencia_preliminar", metricas=None)
                complemento = self.resultado(metricas={"input_tokens": 5, "output_tokens": 2, "total_tokens": 7})
                comecaram = []

                def tentativa(**kwargs):
                    comecaram.append(kwargs)
                    return local if len(comecaram) == 1 else complemento

                with (
                    patch("barreira_persistente.BarreiraPersistente", BarreiraFalsa),
                    patch("complementacoes.aplicar_complementacao", return_value={
                        "pedido_original": original, "pedido_corrigido": corrigido,
                    }),
                    patch("persistencia_sessoes.registrar_diligencia", return_value=SimpleNamespace(
                        session_id=protocolo, user_id=None,
                    )) as reg_diligencia,
                    patch("persistencia_sessoes.registrar_complementacao") as reg_complemento,
                    patch("persistencia_sessoes.preparar_pedido_complementado", return_value=preparado),
                    patch("execucao_interativa.executar_tentativa", side_effect=tentativa),
                ):
                    eventos = []
                    resultado = lote._executar_complementacao_real(
                        protocolo, lambda registro: eventos.append(registro),
                    )

                self.assertEqual(len(eventos), 1)
                self.assertEqual(eventos[0]["tipo_execucao"], "diligencia_preliminar")
                self.assertEqual(len(comecaram), 2)
                self.assertEqual(comecaram[0]["session_id"], protocolo)
                self.assertIsNone(comecaram[0]["user_id"])
                self.assertEqual(comecaram[1]["session_id"], protocolo)
                self.assertEqual(comecaram[1]["user_id"], titular)
                self.assertEqual(comecaram[1]["pedido"], corrigido)
                self.assertTrue(comecaram[1]["usar_memoria"])
                self.assertEqual(reg_diligencia.call_args.kwargs["caminho_banco"], reg_complemento.call_args.kwargs["caminho_banco"])
                self.assertTrue(resultado["correcao_validada"])
                self.assertTrue(resultado["sessao_original_preservada"])
                self.assertTrue(resultado["titular_corrigido_utilizado"])

    def test_falha_de_pedido_grava_checkpoint_e_interrompe_sequencia(self):
        chamadas = []

        def pedido(protocolo):
            chamadas.append(protocolo)
            if len(chamadas) == 2:
                raise ConnectionError("nao registrar mensagem bruta")
            return self.resultado(metricas={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2})

        manifesto = lote.executar_lote(pedido, lambda *_: self.fail("complementacao nao esperada"), diretorio_saida=self.saida)
        self.assertEqual(manifesto["estado"], "interrompido")
        self.assertEqual(chamadas, list(lote.PEDIDOS_COMUNS[:2]))
        falha = json.loads((self.saida / "02_DIA-2026-0102.json").read_text(encoding="utf-8"))
        self.assertEqual(falha["classe_erro"], "ConnectionError")
        self.assertNotIn("nao registrar mensagem bruta", (self.saida / "manifesto.json").read_text(encoding="utf-8"))

    def test_recusa_sobrepor_diretorio_de_resultados(self):
        self.saida.mkdir()
        with self.assertRaises(FileExistsError):
            lote.executar_lote(lambda _: {}, lambda *_: {}, diretorio_saida=self.saida)

    def test_executor_nao_referencia_gabarito(self):
        codigo = (BASE / "testes" / "executar_lote_final.py").read_text(encoding="utf-8")
        self.assertNotIn("gabarito.json", codigo)

    def test_retries_do_agno_guidance_e_cliente_ficam_desativados(self):
        modelo = SimpleNamespace(retries=3, retry_with_guidance=True, max_retries=2)
        lote._desativar_retentativas_automaticas(SimpleNamespace(model=modelo))
        self.assertEqual(modelo.retries, 0)
        self.assertFalse(modelo.retry_with_guidance)
        self.assertEqual(modelo.max_retries, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
