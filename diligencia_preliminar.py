from pathlib import Path

from modelos import Instrucao, Verificacao
from validacao_pedido import validar_pedido


def criar_instrucao_diligencia(pedido: dict) -> Instrucao:
    """
    Produz diligencia preliminar deterministica.

    Nao realiza calculo de diarias, consulta de historico,
    consulta orcamentaria ou chamada ao modelo de IA.
    """

    validacao = validar_pedido(pedido)

    if validacao["pode_analisar_merito"]:
        raise ValueError(
            "Pedido completo: nao exige diligencia preliminar."
        )

    pendencias = list(validacao["pendencias"])

    divergencia_cadastral = any(
        "diverge do cadastro" in item
        or "Matricula nao localizada" in item
        for item in pendencias
    )

    situacao_cadastro = (
        "nao_atende" if divergencia_cadastral else "atende"
    )

    verificacoes = [
        Verificacao(
            criterio="cadastro",
            situacao=situacao_cadastro,
            detalhe=(
                "Ha inconsistencia cadastral que exige saneamento."
                if divergencia_cadastral
                else "Nome e matricula conferidos no cadastro."
            ),
        ),
        Verificacao(
            criterio="dados_completos",
            situacao=(
                "atende"
                if all(
                    pedido.get(campo) is not None
                    and str(pedido.get(campo)).strip()
                    for campo in (
                        "numero",
                        "matricula",
                        "nome",
                        "destino_municipio",
                        "destino_uf",
                        "data_partida",
                        "data_retorno",
                        "justificativa",
                    )
                )
                else "nao_atende"
            ),
            detalhe=(
                "Campos obrigatorios preenchidos; "
                "inconsistencia cadastral impede analise de merito."
                if divergencia_cadastral
                else "; ".join(pendencias)
            ),
        ),
    ]

    for criterio in (
        "antecedencia",
        "prestacao_contas",
        "limite_mensal",
        "saldo_orcamentario",
    ):
        verificacoes.append(
            Verificacao(
                criterio=criterio,
                situacao="nao_verificado",
                detalhe=(
                    "Analise de merito suspensa ate "
                    "a regularizacao dos dados preliminares."
                ),
            )
        )

    numero = str(pedido.get("numero") or "")
    matricula = str(pedido.get("matricula") or "")

    if not numero or not matricula:
        raise ValueError(
            "Numero e matricula sao necessarios "
            "para registrar a diligencia."
        )

    descricao = "; ".join(pendencias)

    return Instrucao(
        numero_pedido=numero,
        matricula=matricula,
        quantidade_diarias=None,
        valor_total=None,
        verificacoes=verificacoes,
        recomendacao="diligencia",
        exige_autorizacao_superior=False,
        pendencias=pendencias,
        alertas=[
            "Analise de merito nao realizada.",
            "Nao houve calculo ou autorizacao de diarias.",
            "A decisao final cabe ao ordenador de despesa.",
        ],
        minuta_despacho=(
            f"Em analise preliminar do pedido {numero}, "
            f"foram identificadas as seguintes pendencias: "
            f"{descricao}. Restituam-se os autos para "
            "complementacao ou correcao das informacoes. "
            "Apos o saneamento, realize-se nova analise "
            "de merito. Esta instrucao nao constitui "
            "autorizacao de concessao ou pagamento."
        ),
    )


if __name__ == "__main__":
    from agente import obter_pedido

    for numero in (
        "DIA-2026-0111",
        "DIA-2026-0112",
    ):
        pedido = obter_pedido(numero)
        instrucao = criar_instrucao_diligencia(pedido)

        print("=" * 70)
        print("PEDIDO:", numero)
        print("RECOMENDACAO:", instrucao.recomendacao)
        print("QUANTIDADE:", instrucao.quantidade_diarias)
        print("VALOR:", instrucao.valor_total)
        print("VERIFICACOES:", len(instrucao.verificacoes))
        print("PENDENCIAS:", instrucao.pendencias)

        for item in instrucao.verificacoes:
            print(
                f"  {item.criterio}: {item.situacao}"
            )

    print("\nNenhuma chamada a API realizada.")
