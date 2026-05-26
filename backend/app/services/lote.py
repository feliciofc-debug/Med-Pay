"""Service de Lote — orquestra upload, listagem, aprovação, retorno.

Centraliza as regras de negócio de lote:
- Idempotência (hash único)
- Mudança de status com validação
- Aprovação dupla com auditoria
- Geração de CNAB no momento da aprovação
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import (
    EmpresaConfigNaoEncontradaError,
    LoteJaProcessadoError,
    LoteNaoAprovavelError,
    LoteNaoEncontradoError,
)
from app.models.cliente import Cliente
from app.models.empresa_config import EmpresaConfig
from app.models.lote import Lote, StatusLote
from app.models.pagamento import Pagamento, StatusPagamento
from app.models.user import User
from app.services.auditoria import AuditoriaService
from app.services.cnab_generator import CNABResult
from app.services.cnab_factory import criar_gerador_cnab
from app.services.importacao import (
    ResultadoImportacao,
    importar_planilha,
)

log = structlog.get_logger()

# Diretórios de armazenamento (configuráveis no futuro via Settings)
UPLOADS_DIR = Path("./storage/uploads")
CNAB_DIR = Path("./storage/cnab")


class LoteService:
    """Encapsula regras de negócio de Lote."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ============================================================
    # Criação de lote a partir de upload
    # ============================================================

    async def criar_a_partir_de_upload(
        self,
        *,
        conteudo: bytes,
        nome_arquivo: str,
        cliente: Cliente,
        enviado_por: User | None = None,
    ) -> tuple[Lote, ResultadoImportacao]:
        """Recebe bytes de planilha, valida, persiste o Lote em RECEBIDO.

        Idempotência: se já existir lote com mesmo hash, retorna esse lote
        em vez de criar novo (e levanta `LoteJaProcessadoError` para o
        chamador decidir o que fazer).

        Returns:
            (Lote, ResultadoImportacao) — lote persistido + linhas extraídas
        """
        importacao = importar_planilha(
            conteudo,
            nome_arquivo,
            mapeamento_cliente=cliente.mapeamento_colunas,  # type: ignore[arg-type]
        )

        # Idempotência por hash
        existente_q = await self.db.execute(
            select(Lote).where(Lote.hash_conteudo == importacao.hash_conteudo)
        )
        existente = existente_q.scalar_one_or_none()
        if existente is not None:
            raise LoteJaProcessadoError(
                f"Este arquivo já foi processado em "
                f"{existente.created_at.strftime('%d/%m/%Y %H:%M')}",
                details={"lote_existente_id": str(existente.id)},
            )

        # Salva conteúdo bruto em disco
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        caminho = UPLOADS_DIR / f"{importacao.hash_conteudo[:16]}_{nome_arquivo}"
        caminho.write_bytes(conteudo)

        lote = Lote(
            cliente_id=cliente.id,
            nome_arquivo=nome_arquivo,
            hash_conteudo=importacao.hash_conteudo,
            referencia=None,
            status=StatusLote.RECEBIDO,
            total_pagamentos=importacao.total_linhas,
            caminho_arquivo_original=str(caminho),
            enviado_por_id=enviado_por.id if enviado_por else None,
        )
        self.db.add(lote)
        await self.db.flush()

        log.info(
            "lote.criado",
            lote_id=str(lote.id),
            cliente_id=str(cliente.id),
            total_linhas=importacao.total_linhas,
            hash=importacao.hash_conteudo[:8],
        )
        return lote, importacao

    # ============================================================
    # Recuperação
    # ============================================================

    async def get(self, lote_id: UUID) -> Lote:
        """Carrega um lote pelo ID. Levanta se não existir."""
        result = await self.db.execute(
            select(Lote)
            .where(Lote.id == lote_id)
            .options(selectinload(Lote.cliente))
        )
        lote = result.scalar_one_or_none()
        if lote is None:
            raise LoteNaoEncontradoError(f"Lote {lote_id} não encontrado")
        return lote

    async def get_com_pagamentos(self, lote_id: UUID) -> Lote:
        """Carrega lote + pagamentos (eager)."""
        result = await self.db.execute(
            select(Lote)
            .where(Lote.id == lote_id)
            .options(
                selectinload(Lote.pagamentos),
                selectinload(Lote.cliente),
            )
        )
        lote = result.scalar_one_or_none()
        if lote is None:
            raise LoteNaoEncontradoError(f"Lote {lote_id} não encontrado")
        return lote

    async def listar(
        self,
        *,
        status: StatusLote | None = None,
        cliente_id: UUID | None = None,
        enviado_por_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Lote]:
        """Lista lotes com filtros opcionais."""
        query = (
            select(Lote)
            .options(selectinload(Lote.cliente))
            .order_by(Lote.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status is not None:
            query = query.where(Lote.status == status)
        if cliente_id is not None:
            query = query.where(Lote.cliente_id == cliente_id)
        if enviado_por_id is not None:
            query = query.where(Lote.enviado_por_id == enviado_por_id)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ============================================================
    # Aprovação + geração CNAB
    # ============================================================

    async def aprovar(
        self,
        lote_id: UUID,
        *,
        aprovador: User,
        observacoes: str | None = None,
        confirmacao_total_centavos: int,
        confirmacao_qtd_pagamentos: int,
    ) -> CNABResult:
        """Aprova um lote, gera o CNAB e registra auditoria.

        Aprovação dupla via confirmação dos totalizadores:
        o frontend envia a soma + qtd que ele exibiu ao operador, e o
        backend só aprova se baterem com os valores reais. Isso protege
        contra race condition (lote alterado entre exibir e aprovar).

        Raises:
            LoteNaoAprovavelError: status não permite aprovação ou totais não batem
            EmpresaConfigNaoEncontradaError: sem dados pra montar o CNAB
        """
        lote = await self.get_com_pagamentos(lote_id)

        if not lote.pode_aprovar:
            raise LoteNaoAprovavelError(
                f"Lote em status {lote.status.value} não pode ser aprovado "
                f"(precisa estar em AGUARDANDO_REVISAO)"
            )

        # Verifica que totais conferem (anti-race-condition)
        # Considera apenas pagamentos válidos + corrigíveis (não bloqueados)
        pagamentos_aprovaveis = [
            p
            for p in lote.pagamentos
            if p.status in (StatusPagamento.VALIDO, StatusPagamento.CORRIGIVEL)
        ]
        soma_real = sum(p.valor_centavos for p in pagamentos_aprovaveis)
        qtd_real = len(pagamentos_aprovaveis)

        if soma_real != confirmacao_total_centavos or qtd_real != confirmacao_qtd_pagamentos:
            raise LoteNaoAprovavelError(
                "Totais informados não batem com o lote. "
                f"Esperado: {qtd_real} pagamentos totalizando R$ {soma_real / 100:.2f}. "
                f"Recebido: {confirmacao_qtd_pagamentos} pagamentos totalizando "
                f"R$ {confirmacao_total_centavos / 100:.2f}.",
                details={
                    "qtd_real": qtd_real,
                    "valor_total_real_centavos": soma_real,
                },
            )

        # Marca todos pagamentos válidos/corrigíveis como APROVADO
        for pagamento in pagamentos_aprovaveis:
            pagamento.status = StatusPagamento.APROVADO

        # Carrega EmpresaConfig ativa
        empresa_q = await self.db.execute(
            select(EmpresaConfig).where(EmpresaConfig.ativo.is_(True)).limit(1)
        )
        empresa = empresa_q.scalar_one_or_none()
        if empresa is None:
            raise EmpresaConfigNaoEncontradaError(
                "Configuração da empresa pagadora ainda não foi cadastrada. "
                "Cadastre os dados Unicred antes de aprovar lotes."
            )

        # Gera CNAB usando o adapter do banco emissor configurado na empresa
        gerador = criar_gerador_cnab(
            lote=lote,
            pagamentos=pagamentos_aprovaveis,
            empresa=empresa,
            numero_sequencial_arquivo=empresa.proximo_numero_sequencial,
        )
        cnab = gerador.gerar()

        # Persiste o CNAB no banco (disco do Render é efêmero — sumia a
        # cada deploy). Mantemos cópia em disco como cache opcional.
        try:
            CNAB_DIR.mkdir(parents=True, exist_ok=True)
            caminho_cnab = CNAB_DIR / cnab.nome_arquivo
            caminho_cnab.write_bytes(cnab.conteudo_bytes)
            lote.caminho_arquivo_cnab = str(caminho_cnab)
        except OSError:
            # Disco read-only/cheio: ok, conteúdo está no banco.
            lote.caminho_arquivo_cnab = None

        lote.status = StatusLote.APROVADO
        lote.aprovado_por_id = aprovador.id
        lote.aprovado_at = datetime.now(UTC)
        lote.observacoes_aprovacao = observacoes
        lote.hash_arquivo_cnab = cnab.hash_sha256
        lote.nome_arquivo_cnab = cnab.nome_arquivo
        lote.conteudo_arquivo_cnab = cnab.conteudo_bytes

        # Incrementa sequencial da empresa
        empresa.proximo_numero_sequencial += 1

        # Auditoria
        auditoria = AuditoriaService(self.db)
        await auditoria.registrar(
            acao="LOTE_APROVADO",
            user=aprovador,
            entidade_tipo="Lote",
            entidade_id=lote.id,
            hash_relacionado=cnab.hash_sha256,
            detalhes={
                "qtd_pagamentos": cnab.quantidade_pagamentos,
                "valor_total_centavos": cnab.valor_total_centavos,
                "nome_arquivo_cnab": cnab.nome_arquivo,
                "qtd_registros_arquivo": cnab.quantidade_registros,
            },
            mensagem=(
                f"Lote {lote.referencia or lote.nome_arquivo} aprovado "
                f"({cnab.quantidade_pagamentos} pagamentos, "
                f"R$ {cnab.valor_total_centavos / 100:.2f})"
            ),
        )

        await self.db.flush()

        log.info(
            "lote.aprovado",
            lote_id=str(lote.id),
            aprovador=aprovador.email,
            qtd=cnab.quantidade_pagamentos,
            valor_centavos=cnab.valor_total_centavos,
            hash_cnab=cnab.hash_sha256[:16],
        )

        return cnab

    # ============================================================
    # Regeração de CNAB (lote já aprovado, mas arquivo perdeu em disco)
    # ============================================================

    async def regerar_cnab(self, lote: Lote) -> tuple[bytes, str]:
        """Regera o CNAB de um lote já aprovado e persiste no banco.

        Usado quando o arquivo em disco sumiu (deploy do Render é efêmero)
        e ainda não tínhamos persistência de bytes no banco. Não incrementa
        o sequencial da empresa: reaproveita o próximo livre só para regerar
        bytes válidos. O hash pode diferir do original.
        """
        if lote.status not in (StatusLote.APROVADO, StatusLote.ENVIADO_BANCO):
            raise LoteNaoAprovavelError(
                f"Lote em status {lote.status.value} não tem CNAB para regerar"
            )

        pagamentos_aprovados = [
            p
            for p in lote.pagamentos
            if p.status == StatusPagamento.APROVADO
        ]
        if not pagamentos_aprovados:
            raise LoteNaoAprovavelError(
                "Lote aprovado, mas sem pagamentos aprovados para regerar CNAB"
            )

        empresa_q = await self.db.execute(
            select(EmpresaConfig).where(EmpresaConfig.ativo.is_(True)).limit(1)
        )
        empresa = empresa_q.scalar_one_or_none()
        if empresa is None:
            raise EmpresaConfigNaoEncontradaError(
                "Configuração da empresa pagadora não encontrada"
            )

        gerador = criar_gerador_cnab(
            lote=lote,
            pagamentos=pagamentos_aprovados,
            empresa=empresa,
            numero_sequencial_arquivo=empresa.proximo_numero_sequencial,
        )
        cnab = gerador.gerar()

        lote.nome_arquivo_cnab = cnab.nome_arquivo
        lote.hash_arquivo_cnab = cnab.hash_sha256
        lote.conteudo_arquivo_cnab = cnab.conteudo_bytes
        # Consome o sequencial: esse arquivo vai pro banco; o próximo lote
        # aprovado tem que sair com o número seguinte.
        empresa.proximo_numero_sequencial += 1
        await self.db.flush()

        log.info(
            "lote.cnab_regerado",
            lote_id=str(lote.id),
            hash_cnab=cnab.hash_sha256[:16],
        )

        return cnab.conteudo_bytes, cnab.nome_arquivo

    # ============================================================
    # Marcação de envio ao banco (manual)
    # ============================================================

    async def marcar_enviado_ao_banco(
        self, lote_id: UUID, *, aprovador: User
    ) -> Lote:
        """Operador clica 'já enviei o CNAB no internet banking'."""
        lote = await self.get(lote_id)
        if lote.status != StatusLote.APROVADO:
            raise LoteNaoAprovavelError(
                f"Lote em status {lote.status.value} não pode ser marcado "
                f"como enviado (precisa estar em APROVADO)"
            )
        lote.status = StatusLote.ENVIADO_BANCO

        auditoria = AuditoriaService(self.db)
        await auditoria.registrar(
            acao="LOTE_ENVIADO_BANCO",
            user=aprovador,
            entidade_tipo="Lote",
            entidade_id=lote.id,
            mensagem=f"Operador confirmou envio do CNAB ao banco",
        )
        await self.db.flush()
        return lote


__all__ = ["LoteService"]
