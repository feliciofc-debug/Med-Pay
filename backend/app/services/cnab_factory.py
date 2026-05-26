"""Factory de geradores CNAB — escolhe o adapter pelo banco emissor.

Centraliza a decisão de qual classe CNAB usar (`CNABGeneratorUnicred`,
`CNABGeneratorItau`, `CNABGeneratorBradesco`) baseado no campo
`empresa.banco_emissor`.

Adicionar um banco novo:
    1. Criar `cnab_<banco>.py` herdando de CNABGeneratorBase
    2. Registrar no dicionário ADAPTERS abaixo
    3. Adicionar o valor no enum BancoEmissor
    4. Criar migration adicionando o valor no ENUM banco_emissor_cnab
"""

from __future__ import annotations

from datetime import datetime

from app.models.empresa_config import BancoEmissor, EmpresaConfig
from app.models.lote import Lote
from app.models.pagamento import Pagamento
from app.services.cnab_base import CNABGeneratorBase, CNABGeneratorError
from app.services.cnab_bradesco import CNABGeneratorBradesco
from app.services.cnab_itau import CNABGeneratorItau
from app.services.cnab_unicred import CNABGeneratorUnicred

ADAPTERS: dict[BancoEmissor, type[CNABGeneratorBase]] = {
    BancoEmissor.UNICRED: CNABGeneratorUnicred,
    BancoEmissor.ITAU: CNABGeneratorItau,
    BancoEmissor.BRADESCO: CNABGeneratorBradesco,
}


def criar_gerador_cnab(
    *,
    lote: Lote,
    pagamentos: list[Pagamento],
    empresa: EmpresaConfig,
    numero_sequencial_arquivo: int,
    codigo_lote_no_arquivo: int = 1,
    agora: datetime | None = None,
) -> CNABGeneratorBase:
    """Retorna o gerador apropriado conforme `empresa.banco_emissor`.

    Se o banco emissor não estiver mapeado (instância antiga sem coluna,
    ou enum desatualizado), cai pra Unicred — o comportamento padrão do
    MVP — em vez de explodir.
    """
    banco = getattr(empresa, "banco_emissor", None) or BancoEmissor.UNICRED
    adapter_cls = ADAPTERS.get(banco)
    if adapter_cls is None:
        raise CNABGeneratorError(
            f"Banco emissor {banco!r} não tem adapter CNAB cadastrado. "
            f"Bancos suportados: {[b.value for b in ADAPTERS]}"
        )
    return adapter_cls(
        lote=lote,
        pagamentos=pagamentos,
        empresa=empresa,
        numero_sequencial_arquivo=numero_sequencial_arquivo,
        codigo_lote_no_arquivo=codigo_lote_no_arquivo,
        agora=agora,
    )


__all__ = ["ADAPTERS", "criar_gerador_cnab"]
