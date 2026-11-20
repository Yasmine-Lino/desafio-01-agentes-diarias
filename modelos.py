from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Verificacao(BaseModel):
    """Resultado de uma verificacao normativa."""

    model_config = ConfigDict(extra="forbid")

    criterio: Literal[
        "cadastro",
        "dados_completos",
        "antecedencia",
        "prestacao_contas",
        "limite_mensal",
        "saldo_orcamentario",
    ]

    situacao: Literal[
        "atende",
        "nao_atende",
        "nao_verificado",
    ]

    detalhe: str = Field(min_length=1)


class Instrucao(BaseModel):
    """Instrucao estruturada de um pedido de diarias."""

    model_config = ConfigDict(extra="forbid")

    numero_pedido: str = Field(min_length=1)
    matricula: str = Field(min_length=1)

    quantidade_diarias: float | None
    valor_total: float | None

    verificacoes: list[Verificacao]

    recomendacao: Literal[
        "apto_para_autorizacao",
        "diligencia",
        "nao_recomendado",
    ]

    exige_autorizacao_superior: bool

    pendencias: list[str]
    alertas: list[str]
    minuta_despacho: str = Field(min_length=1)

    @model_validator(mode="after")
    def validar_verificacoes(self):
        criterios_esperados = {
            "cadastro",
            "dados_completos",
            "antecedencia",
            "prestacao_contas",
            "limite_mensal",
            "saldo_orcamentario",
        }

        criterios_recebidos = [
            item.criterio for item in self.verificacoes
        ]

        if (
            len(criterios_recebidos) != 6
            or set(criterios_recebidos) != criterios_esperados
        ):
            raise ValueError(
                "A instrucao deve conter exatamente "
                "as seis verificacoes, sem duplicatas."
            )

        for campo in ("quantidade_diarias", "valor_total"):
            valor = getattr(self, campo)

            if valor is not None:
                import math

                if not math.isfinite(valor) or valor < 0:
                    raise ValueError(
                        f"{campo} deve ser um numero "
                        "finito e nao negativo."
                    )

        return self
