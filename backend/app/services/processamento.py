"""Processamento de lote — orquestra validações e gera Pagamentos.

Recebe um Lote em status RECEBIDO + as linhas brutas da planilha,
roda os validators (CPF, banco, valor), detecta duplicatas dentro do
próprio lote, e cria registros Pagamento no banco com criptografia
dos campos sensíveis.

REGRAS DE NEGÓCIO:
- CPF/conta criptografados via Fernet (`core.crypto.encrypt`)
- Hash determinístico (SHA-256) pra busca/dedup
- CPF/conta mascarados pra exibição em listas
- Valores em centavos (BigInteger)
- Status do pagamento derivado das validações:
    - todas OK             → VALIDO
    - alguma CORRIGIVEL    → CORRIGIVEL (sugestão para revisão)
    - qualquer BLOQUEADO   → BLOQUEADO (não pode ser enviado)
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt, hash_for_lookup, mask_conta, mask_cpf
from app.models.beneficiario import Beneficiario
from app.models.lote import Lote, StatusLote
from app.models.pagamento import ModalidadePagamento, Pagamento, StatusPagamento
from app.services.importacao import LinhaPlanilha
from app.validators.banco import StatusBanco, validar_dados_bancarios
from app.validators.cpf import CPFStatus, limpar_cpf, validar_cpf
from app.validators.valor import ValorStatus, validar_valor

# Código FEBRABAN da Unicred (banco pagador). Se o favorecido também é
# Unicred, a transferência é interna (forma_lanc 41) ao invés de TED.
_CODIGO_UNICRED = "136"


@dataclass(slots=True)
class ResumoLinha:
    """Resumo das validações de uma linha (antes de virar Pagamento)."""

    linha: LinhaPlanilha
    status: StatusPagamento
    codigos_erro: list[str]
    mensagens: list[str]
    cpf_limpo: str | None
    cpf_sugerido: str | None
    cpf_mascarado: str
    valor_centavos: int  # 0 se não pôde parsear
    nome: str
    banco_codigo: str | None
    agencia_limpa: str | None
    conta_limpa: str | None
    modalidade: ModalidadePagamento = ModalidadePagamento.TED
    chave_pix: str | None = None


@dataclass(slots=True)
class ResultadoProcessamento:
    """Resumo do processamento de um lote inteiro."""

    total: int
    validos: int
    corrigiveis: int
    bloqueados: int
    valor_total_centavos: int


# ============================================================
# Validação de uma única linha (orquestra validators)
# ============================================================


def _decidir_modalidade(
    banco_codigo: str | None,
    chave_pix: str | None,
) -> ModalidadePagamento:
    """Decide a modalidade de envio do pagamento.

    Regras (alinhadas com o template Unicred do Thiago):
    1. Se tem chave PIX → PIX (mais rápido e barato)
    2. Senão se banco destino é Unicred (136) → TRANSF_UNICRED (intra-banco)
    3. Senão → TED (default, sempre funciona)

    Hoje a planilha do hospital não traz chave PIX, então o default vai
    cair em TRANSF_UNICRED ou TED. Quando integrarmos cadastro de
    beneficiários (Sprint 2), passa a fazer PIX por chave automaticamente.
    """
    if chave_pix:
        return ModalidadePagamento.PIX
    if banco_codigo == _CODIGO_UNICRED:
        return ModalidadePagamento.TRANSF_UNICRED
    return ModalidadePagamento.TED


def _validar_linha(linha: LinhaPlanilha) -> ResumoLinha:
    """Roda todos os validators e consolida o resultado."""
    codigos: list[str] = []
    mensagens: list[str] = []

    # CPF
    res_cpf = validar_cpf(linha.cpf_raw)
    cpf_para_uso = res_cpf.cpf_limpo or limpar_cpf(linha.cpf_raw)
    if res_cpf.codigo_erro:
        codigos.append(res_cpf.codigo_erro)
        mensagens.append(res_cpf.mensagem)

    # Valor
    res_valor = validar_valor(linha.valor_raw)
    if res_valor.codigo_erro:
        codigos.append(res_valor.codigo_erro)
        mensagens.append(res_valor.mensagem)

    # Banco
    res_banco = validar_dados_bancarios(linha.banco_raw, linha.agencia_raw, linha.conta_raw)
    if res_banco.codigo_erro:
        codigos.append(res_banco.codigo_erro)
        mensagens.append(res_banco.mensagem)

    # Determina status final
    if (
        res_cpf.status == CPFStatus.INVALIDO
        or res_banco.status == StatusBanco.INVALIDO
        or res_banco.status == StatusBanco.NAO_SUPORTADO
        or res_valor.status == ValorStatus.INVALIDO
    ):
        status = StatusPagamento.BLOQUEADO
    elif (
        res_cpf.status == CPFStatus.CORRIGIVEL
        or res_valor.status == ValorStatus.SUSPEITO
    ):
        status = StatusPagamento.CORRIGIVEL
    else:
        status = StatusPagamento.VALIDO

    nome = (linha.nome_raw or "").strip()
    if not nome:
        codigos.append("NOME_VAZIO")
        mensagens.append("Nome do beneficiário não informado")
        status = StatusPagamento.BLOQUEADO

    modalidade = _decidir_modalidade(res_banco.banco_codigo, chave_pix=None)

    return ResumoLinha(
        linha=linha,
        status=status,
        codigos_erro=codigos,
        mensagens=mensagens,
        cpf_limpo=cpf_para_uso or None,
        cpf_sugerido=res_cpf.cpf_sugerido,
        cpf_mascarado=mask_cpf(cpf_para_uso) if cpf_para_uso else "***",
        valor_centavos=res_valor.valor_centavos or 0,
        nome=nome,
        banco_codigo=res_banco.banco_codigo,
        agencia_limpa=res_banco.agencia_limpa,
        conta_limpa=res_banco.conta_limpa,
        modalidade=modalidade,
        chave_pix=None,
    )


# ============================================================
# Detecção de duplicata interna ao lote
# ============================================================


def _detectar_duplicatas(resumos: list[ResumoLinha]) -> set[int]:
    """Retorna índices das linhas duplicadas (mesmo CPF + valor no lote).

    A primeira ocorrência NÃO é marcada como duplicata. Apenas as repetições.
    """
    chave_to_indices: dict[tuple[str, int], list[int]] = {}
    for idx, r in enumerate(resumos):
        if not r.cpf_limpo or not r.valor_centavos:
            continue
        chave = (r.cpf_limpo, r.valor_centavos)
        chave_to_indices.setdefault(chave, []).append(idx)

    duplicadas: set[int] = set()
    for indices in chave_to_indices.values():
        if len(indices) > 1:
            duplicadas.update(indices[1:])
    return duplicadas


# ============================================================
# Construção do Pagamento (com criptografia)
# ============================================================


def _construir_pagamento(
    lote: Lote,
    resumo: ResumoLinha,
    beneficiario_id: UUID | None = None,
) -> Pagamento:
    """Cria registro Pagamento com criptografia dos campos sensíveis."""
    cpf_limpo = resumo.cpf_limpo or ""

    # CPF: criptografado SEMPRE (mesmo se inválido — auditoria precisa do valor original)
    cpf_para_encrypt = cpf_limpo or (resumo.linha.cpf_raw or "INVALIDO")
    cpf_encrypted = encrypt(cpf_para_encrypt)
    cpf_hash = hash_for_lookup(cpf_para_encrypt)

    # Conta: criptografada se houver
    agencia_encrypted = encrypt(resumo.agencia_limpa) if resumo.agencia_limpa else None
    conta_encrypted = encrypt(resumo.conta_limpa) if resumo.conta_limpa else None
    conta_mascarada = mask_conta(resumo.conta_limpa) if resumo.conta_limpa else None

    return Pagamento(
        lote_id=lote.id,
        beneficiario_id=beneficiario_id,
        linha_planilha=resumo.linha.numero_linha,
        cpf_encrypted=cpf_encrypted,
        cpf_hash=cpf_hash,
        cpf_mascarado=resumo.cpf_mascarado,
        cpf_original=resumo.linha.cpf_raw,
        nome=resumo.nome,
        banco_codigo=resumo.banco_codigo,
        agencia_encrypted=agencia_encrypted,
        conta_encrypted=conta_encrypted,
        conta_mascarada=conta_mascarada,
        valor_centavos=resumo.valor_centavos,
        modalidade=resumo.modalidade,
        chave_pix=resumo.chave_pix,
        status=resumo.status,
        codigos_erro=",".join(resumo.codigos_erro) if resumo.codigos_erro else None,
        mensagens_validacao=(
            json.dumps(resumo.mensagens, ensure_ascii=False)
            if resumo.mensagens
            else None
        ),
        cpf_sugerido=resumo.cpf_sugerido,
    )


async def _carregar_beneficiarios_por_cpf(
    db: AsyncSession, cliente_id: UUID, cpf_hashes: set[str]
) -> dict[str, UUID]:
    """Monta dict {cpf_hash: beneficiario_id} pra casar de uma vez.

    Roda 1 query por lote (não N+1). Limita-se a beneficiários ATIVOS
    do cliente em questão (UniqueConstraint cliente_id+cpf_hash garante
    no máximo 1 resultado por CPF).
    """
    if not cpf_hashes:
        return {}
    result = await db.execute(
        select(Beneficiario.id, Beneficiario.cpf_hash).where(
            Beneficiario.cliente_id == cliente_id,
            Beneficiario.ativo.is_(True),
            Beneficiario.cpf_hash.in_(cpf_hashes),
        )
    )
    return {row.cpf_hash: row.id for row in result.all()}


# ============================================================
# Função orquestradora principal
# ============================================================


async def processar_lote(
    db: AsyncSession,
    lote: Lote,
    linhas: list[LinhaPlanilha],
) -> ResultadoProcessamento:
    """Processa um lote: valida cada linha, cria Pagamentos, atualiza totais.

    Args:
        db: sessão SQLAlchemy
        lote: Lote em status RECEBIDO ou PROCESSANDO
        linhas: linhas brutas vindas do importador

    Returns:
        ResultadoProcessamento com totais
    """
    lote.status = StatusLote.PROCESSANDO
    await db.flush()

    # 1. Valida cada linha
    resumos = [_validar_linha(linha) for linha in linhas]

    # 2. Detecta duplicatas e marca
    duplicadas = _detectar_duplicatas(resumos)
    for idx in duplicadas:
        r = resumos[idx]
        r.codigos_erro.append("PAGAMENTO_DUPLICADO")
        r.mensagens.append(
            "Possível duplicata: mesmo CPF e valor já aparecem em outra linha do lote"
        )
        # Promove para CORRIGIVEL no mínimo (não bloqueia, é um aviso)
        if r.status == StatusPagamento.VALIDO:
            resumos[idx] = ResumoLinha(
                linha=r.linha,
                status=StatusPagamento.CORRIGIVEL,
                codigos_erro=r.codigos_erro,
                mensagens=r.mensagens,
                cpf_limpo=r.cpf_limpo,
                cpf_sugerido=r.cpf_sugerido,
                cpf_mascarado=r.cpf_mascarado,
                valor_centavos=r.valor_centavos,
                nome=r.nome,
                banco_codigo=r.banco_codigo,
                agencia_limpa=r.agencia_limpa,
                conta_limpa=r.conta_limpa,
            )

    # 3. Casa CPF com Beneficiário cadastrado (preenche beneficiario_id)
    #    Importante pra modalidade PIX, contratos por médico e relatórios
    #    que partem de "lista de prestadores".
    hashes_validos = {
        hash_for_lookup(r.cpf_limpo) for r in resumos if r.cpf_limpo
    }
    mapa_beneficiarios = await _carregar_beneficiarios_por_cpf(
        db, lote.cliente_id, hashes_validos
    )

    pagamentos: list[Pagamento] = []
    for r in resumos:
        ben_id: UUID | None = None
        if r.cpf_limpo:
            ben_id = mapa_beneficiarios.get(hash_for_lookup(r.cpf_limpo))
        pagamentos.append(_construir_pagamento(lote, r, beneficiario_id=ben_id))
    db.add_all(pagamentos)

    # 4. Calcula totais
    cont = Counter(r.status for r in resumos)
    valor_total = sum(
        r.valor_centavos
        for r in resumos
        if r.status in (StatusPagamento.VALIDO, StatusPagamento.CORRIGIVEL)
    )

    lote.total_pagamentos = len(resumos)
    lote.total_validos = cont.get(StatusPagamento.VALIDO, 0)
    lote.total_corrigiveis = cont.get(StatusPagamento.CORRIGIVEL, 0)
    lote.total_bloqueados = cont.get(StatusPagamento.BLOQUEADO, 0)
    lote.valor_total_centavos = valor_total
    lote.status = StatusLote.AGUARDANDO_REVISAO

    await db.flush()

    return ResultadoProcessamento(
        total=lote.total_pagamentos,
        validos=lote.total_validos,
        corrigiveis=lote.total_corrigiveis,
        bloqueados=lote.total_bloqueados,
        valor_total_centavos=lote.valor_total_centavos,
    )


__all__ = [
    "ResultadoProcessamento",
    "ResumoLinha",
    "processar_lote",
]
