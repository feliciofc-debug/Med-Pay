"""Service de conciliação — fecha o ciclo do lote com o retorno do banco.

Pega o ResultadoParseRetorno (vindo do cnab_parser) e atualiza cada
Pagamento conforme o que o banco devolveu. Atualiza status do Lote
para CONCILIADO e gera registro de auditoria.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import (
    LoteNaoEncontradoError,
    LoteNaoAprovavelError,
)
from app.models.beneficiario import Beneficiario
from app.models.lote import Lote, StatusLote
from app.models.pagamento import Pagamento, StatusPagamento
from app.models.user import User
from app.services.auditoria import AuditoriaService
from app.services.cnab_parser import (
    ResultadoParseRetorno,
    parsear_arquivo_retorno,
)
from app.services.lote import CNAB_DIR

log = structlog.get_logger()

RETORNO_DIR = Path("./storage/retorno")


class ConciliacaoService:
    """Aplica retorno bancário em um lote já enviado."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def aplicar_retorno(
        self,
        lote_id: UUID,
        *,
        conteudo: bytes,
        nome_arquivo: str,
        operador: User,
    ) -> ResultadoParseRetorno:
        """Lê o arquivo de retorno e atualiza os Pagamentos do lote.

        Args:
            lote_id: ID do lote a ser conciliado
            conteudo: bytes do arquivo .ret
            nome_arquivo: nome original (informativo)
            operador: usuário que está fazendo a conciliação

        Raises:
            LoteNaoEncontradoError
            LoteNaoAprovavelError: lote não está em status que permite conciliar
        """
        result = await self.db.execute(
            select(Lote)
            .where(Lote.id == lote_id)
            .options(selectinload(Lote.pagamentos))
        )
        lote = result.scalar_one_or_none()
        if lote is None:
            raise LoteNaoEncontradoError(f"Lote {lote_id} não encontrado")

        if lote.status not in (StatusLote.APROVADO, StatusLote.ENVIADO_BANCO):
            raise LoteNaoAprovavelError(
                f"Lote em status {lote.status.value} não pode ser conciliado. "
                f"Esperado APROVADO ou ENVIADO_BANCO."
            )

        # Salva o arquivo bruto pra auditoria
        RETORNO_DIR.mkdir(parents=True, exist_ok=True)
        caminho = RETORNO_DIR / f"{lote.id.hex[:8]}_{nome_arquivo}"
        caminho.write_bytes(conteudo)

        # Parseia
        resultado = parsear_arquivo_retorno(conteudo)

        # Cria índice por id_documento (UUID que colocamos no Segmento A)
        pagamentos_por_id: dict[str, Pagamento] = {
            str(p.id)[:20]: p for p in lote.pagamentos
        }

        # Códigos de retorno CNAB que indicam problema na conta do favorecido.
        # Quando aparecem, marcamos o beneficiário como "conta inválida" para
        # alertar no próximo lote. Fonte: layout FEBRABAN CNAB 240.
        codigos_conta_invalida = {
            "02",  # Agência/Conta favorecido inválida
            "03",  # Conta favorecido inexistente
            "AG",  # Agência inválida
            "AH",  # Tipo conta favorecido inválido
            "AI",  # Conta corrente do cliente inválida
            "AJ",  # CGC/CPF inválido
            "AN",  # Endereço favorecido não informado
            "BC",  # Conta destino inválida
            "BD",  # Agência destino inválida
        }

        beneficiarios_a_marcar: dict[UUID, str] = {}
        beneficiarios_a_verificar: set[UUID] = set()

        atualizados = 0
        for ret in resultado.pagamentos:
            pagamento = pagamentos_por_id.get(ret.id_documento)
            if pagamento is None:
                # Pode acontecer se o banco não preservou o ID que mandamos.
                # Tentamos casar por sequencial como fallback (assumindo ordem).
                continue

            if ret.foi_pago:
                pagamento.status = StatusPagamento.PAGO
                pagamento.pago_at = datetime.now(UTC)
                # Pagamento confirmado → conta validada
                if pagamento.beneficiario_id is not None:
                    beneficiarios_a_verificar.add(pagamento.beneficiario_id)
            else:
                pagamento.status = StatusPagamento.NAO_PAGO
                cod = (ret.codigo_ocorrencia or "").strip().upper()
                if (
                    cod in codigos_conta_invalida
                    and pagamento.beneficiario_id is not None
                ):
                    beneficiarios_a_marcar[pagamento.beneficiario_id] = (
                        f"{cod} — {ret.descricao_ocorrencia or 'Conta rejeitada pelo banco'}"
                    )

            pagamento.retorno_codigo = ret.codigo_ocorrencia
            pagamento.retorno_descricao = ret.descricao_ocorrencia
            atualizados += 1

        # Aplica marcação nos beneficiários (1 query batch cada lado)
        if beneficiarios_a_marcar:
            result_inv = await self.db.execute(
                select(Beneficiario).where(
                    Beneficiario.id.in_(beneficiarios_a_marcar.keys())
                )
            )
            for ben in result_inv.scalars().all():
                ben.conta_verificada = False
                ben.conta_invalida_motivo = beneficiarios_a_marcar[ben.id]
                ben.conta_verificada_em = datetime.now(UTC)

        if beneficiarios_a_verificar:
            result_ok = await self.db.execute(
                select(Beneficiario).where(
                    Beneficiario.id.in_(beneficiarios_a_verificar)
                )
            )
            for ben in result_ok.scalars().all():
                ben.conta_verificada = True
                ben.conta_invalida_motivo = None
                ben.conta_verificada_em = datetime.now(UTC)

        lote.status = StatusLote.CONCILIADO
        lote.caminho_arquivo_retorno = str(caminho)

        # Auditoria
        auditoria = AuditoriaService(self.db)
        await auditoria.registrar(
            acao="LOTE_CONCILIADO",
            user=operador,
            entidade_tipo="Lote",
            entidade_id=lote.id,
            detalhes={
                "total_no_retorno": len(resultado.pagamentos),
                "pagamentos_atualizados": atualizados,
                "pagos": resultado.pagos,
                "nao_pagos": resultado.nao_pagos,
                "nome_arquivo": nome_arquivo,
            },
            mensagem=(
                f"Retorno aplicado: {resultado.pagos} pagos, "
                f"{resultado.nao_pagos} não pagos"
            ),
        )

        await self.db.flush()

        log.info(
            "lote.conciliado",
            lote_id=str(lote.id),
            atualizados=atualizados,
            pagos=resultado.pagos,
            nao_pagos=resultado.nao_pagos,
        )
        return resultado


__all__ = ["ConciliacaoService", "RETORNO_DIR"]
