"""Testes da lógica pura de SCP (distribuição) e validação PIX↔CPF/CNPJ.

Cobrem só as funções PURAS (sem banco/rede): `calcular_distribuicoes` e
`comparar_titularidade`. Garantem que dinheiro fecha em centavos exatos e
que a cadeia de confiança PF/PJ classifica certo.
"""

from __future__ import annotations

from uuid import uuid4

from app.models.scp import ParticipanteSCP, RegraCota
from app.services.pix_validacao import ResultadoPix, comparar_titularidade
from app.services.scp_service import calcular_distribuicoes


def _part(regra: RegraCota, *, pct_bp: int = 0, aporte: int = 0) -> ParticipanteSCP:
    return ParticipanteSCP(
        id=uuid4(),
        cliente_id=uuid4(),
        beneficiario_id=uuid4(),
        regra_cota=regra,
        percentual_bp=pct_bp,
        aporte_centavos=aporte,
        ativo=True,
    )


class TestCalcularDistribuicoes:
    def test_resultado_zero_zera_todos(self) -> None:
        parts = [_part(RegraCota.PERCENTUAL_FIXO, pct_bp=5000)]
        linhas = calcular_distribuicoes(resultado_centavos=0, participantes=parts)
        assert all(l.valor_centavos == 0 for l in linhas)

    def test_sem_participantes(self) -> None:
        assert calcular_distribuicoes(resultado_centavos=10_000, participantes=[]) == []

    def test_percentual_fixo_soma_exata(self) -> None:
        a = _part(RegraCota.PERCENTUAL_FIXO, pct_bp=3000)  # 30%
        b = _part(RegraCota.PERCENTUAL_FIXO, pct_bp=7000)  # 70%
        linhas = calcular_distribuicoes(resultado_centavos=100_000, participantes=[a, b])
        vals = {l.participante_id: l.valor_centavos for l in linhas}
        assert vals[a.id] == 30_000
        assert vals[b.id] == 70_000

    def test_proporcional_servico_usa_bases(self) -> None:
        a = _part(RegraCota.PROPORCIONAL_SERVICO)
        b = _part(RegraCota.PROPORCIONAL_SERVICO)
        bases = {a.beneficiario_id: 3_000, b.beneficiario_id: 1_000}
        linhas = calcular_distribuicoes(
            resultado_centavos=8_000, participantes=[a, b], bases_servico=bases
        )
        vals = {l.participante_id: l.valor_centavos for l in linhas}
        # 3:1 de 8000 -> 6000 / 2000
        assert vals[a.id] == 6_000
        assert vals[b.id] == 2_000
        assert sum(vals.values()) == 8_000

    def test_proporcional_sem_base_e_igualitario(self) -> None:
        a = _part(RegraCota.PROPORCIONAL_SERVICO)
        b = _part(RegraCota.PROPORCIONAL_SERVICO)
        linhas = calcular_distribuicoes(resultado_centavos=10_000, participantes=[a, b])
        vals = {l.participante_id: l.valor_centavos for l in linhas}
        assert vals[a.id] == 5_000
        assert vals[b.id] == 5_000

    def test_por_aporte(self) -> None:
        a = _part(RegraCota.POR_APORTE, aporte=2_000)
        b = _part(RegraCota.POR_APORTE, aporte=2_000)
        c = _part(RegraCota.POR_APORTE, aporte=6_000)
        linhas = calcular_distribuicoes(
            resultado_centavos=10_000, participantes=[a, b, c]
        )
        vals = {l.participante_id: l.valor_centavos for l in linhas}
        assert vals[a.id] == 2_000
        assert vals[b.id] == 2_000
        assert vals[c.id] == 6_000
        assert sum(vals.values()) == 10_000

    def test_misto_fixo_mais_variavel_fecha_em_centavos(self) -> None:
        fixo = _part(RegraCota.PERCENTUAL_FIXO, pct_bp=2000)  # 20%
        v1 = _part(RegraCota.PROPORCIONAL_SERVICO)
        v2 = _part(RegraCota.PROPORCIONAL_SERVICO)
        bases = {v1.beneficiario_id: 1, v2.beneficiario_id: 2}
        resultado = 99_999  # valor "feio" pra forçar arredondamento
        linhas = calcular_distribuicoes(
            resultado_centavos=resultado,
            participantes=[fixo, v1, v2],
            bases_servico=bases,
        )
        total = sum(l.valor_centavos for l in linhas)
        assert total == resultado  # nunca pode sobrar/faltar centavo


class TestCompararTitularidade:
    def test_cpf_confere(self) -> None:
        v = comparar_titularidade(
            cpf_esperado="123.456.789-09", doc_titular="12345678909"
        )
        assert v.resultado == ResultadoPix.CONFERE

    def test_cpf_divergente(self) -> None:
        v = comparar_titularidade(
            cpf_esperado="123.456.789-09", doc_titular="98765432100"
        )
        assert v.resultado == ResultadoPix.DIVERGENTE

    def test_cnpj_vinculado_confere(self) -> None:
        v = comparar_titularidade(
            cpf_esperado="12345678909",
            doc_titular="12.345.678/0001-95",
            cnpjs_vinculados=["12345678000195"],
        )
        assert v.resultado == ResultadoPix.CONFERE

    def test_cnpj_nao_vinculado_divergente(self) -> None:
        v = comparar_titularidade(
            cpf_esperado="12345678909",
            doc_titular="99999999000191",
            cnpjs_vinculados=["12345678000195"],
        )
        assert v.resultado == ResultadoPix.DIVERGENTE

    def test_titular_ausente_pendente(self) -> None:
        v = comparar_titularidade(cpf_esperado="12345678909", doc_titular=None)
        assert v.resultado == ResultadoPix.PENDENTE

    def test_formato_inesperado_pendente(self) -> None:
        v = comparar_titularidade(cpf_esperado="12345678909", doc_titular="123")
        assert v.resultado == ResultadoPix.PENDENTE
