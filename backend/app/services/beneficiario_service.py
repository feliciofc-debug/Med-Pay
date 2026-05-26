"""Service do cadastro mestre de beneficiários (prestadores).

Responsabilidades:
    - CRUD básico (criar, atualizar, listar, buscar, aprovar, desativar)
    - Lookup por CPF dentro do escopo do cliente (usado pelo pipeline OCR)
    - Importação em massa via planilha (XLSX/CSV) com preview + confirmação
      em 2 passos para o admin revisar antes de efetivar.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID
from sqlalchemy import and_, asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import (
    encrypt,
    hash_for_lookup,
    mask_conta,
    mask_cpf,
)
from app.models.beneficiario import (
    Beneficiario,
    OrigemCadastroBeneficiario,
    StatusBeneficiario,
)
from app.models.cliente import Cliente
from app.schemas.beneficiario import (
    BeneficiarioCreateRequest,
    BeneficiarioListResponse,
    BeneficiarioOut,
    BeneficiarioUpdateRequest,
    ImportConfirmRequest,
    ImportConfirmResponse,
    ImportPreviewResponse,
    LinhaImportPreview,
)
from app.services.importacao import _ler_planilha, _normalizar_chave
from app.validators.cpf import validar_cpf

log = logging.getLogger(__name__)


# ============================================================
# Aliases de colunas para a planilha de prestadores
# ============================================================
#
# Cobre os cabeçalhos típicos que hospitais brasileiros usam.
# A normalização (ver `_normalizar_chave`) já remove acentos, espaços,
# pontuação — então variações como "C P F" ou "Razão Social" caem todas
# na mesma chave.
_ALIASES_BENEFICIARIO: dict[str, list[str]] = {
    "cpf": [
        "cpf",
        "documento",
        "doc",
        "cpfprestador",
        "cpfmedico",
        "cpfprofissional",
        "cpfbeneficiario",
        "numerocpf",
    ],
    "nome": [
        "nome",
        "nomecompleto",
        "prestador",
        "medico",
        "profissional",
        "favorecido",
        "beneficiario",
        "razaosocial",
        "nomeprestador",
        "nomedoprestador",
    ],
    "crm": ["crm", "registro", "registroprofissional", "conselho", "coren", "cro"],
    "categoria": ["categoria", "tipo", "funcao", "cargo", "tipoprestador"],
    "especialidade": ["especialidade", "area", "areaatuacao"],
    "email": ["email", "emailprofissional", "mail", "ecorreio"],
    "telefone": ["telefone", "celular", "fone", "whatsapp", "contato"],
    "banco": ["banco", "codigobanco", "codbanco", "bancodestino", "ban"],
    "agencia": ["agencia", "ag", "agenciadestino", "agenciaconta"],
    "conta": [
        "conta",
        "contacorrente",
        "ccdestino",
        "contadestino",
        "ccpoupanca",
        "cc",
        "contadigito",
    ],
    "pix_chave": ["pix", "chavepix", "chave", "pixchave"],
    "pix_tipo": ["tipopix", "tipodachavepix", "pixtipo"],
    "valor_padrao": [
        "valorpadrao",
        "valorhora",
        "valorplantao",
        "valorfixo",
        "valor",
        "valormensal",
        "valorpadraoplantao",
    ],
    "observacoes": ["observacoes", "obs", "comentario", "anotacoes"],
}


def _detectar_mapeamento_beneficiario(colunas: list[str]) -> dict[str, str]:
    """Mapeia campo lógico → nome real da coluna na planilha."""
    mapeamento: dict[str, str] = {}
    colunas_norm = {_normalizar_chave(c): c for c in colunas}
    for campo_logico, aliases in _ALIASES_BENEFICIARIO.items():
        for alias in aliases:
            alias_norm = _normalizar_chave(alias)
            if alias_norm in colunas_norm:
                mapeamento[campo_logico] = colunas_norm[alias_norm]
                break
    return mapeamento


# ============================================================
# Tokenização de previews (cache em memória — TTL curto)
# ============================================================
#
# O wizard de importação tem 2 passos: preview e confirma. Pra evitar
# reupload do arquivo na confirmação, o preview devolve um TOKEN e
# guardamos em memória os dados parseados. TTL de 30 minutos.

_PREVIEW_CACHE: dict[str, dict[str, Any]] = {}
_PREVIEW_TTL_SECS = 30 * 60


def _gc_cache() -> None:
    """Remove tokens expirados do cache."""
    agora = time.time()
    expirados = [t for t, p in _PREVIEW_CACHE.items() if p["exp"] < agora]
    for t in expirados:
        _PREVIEW_CACHE.pop(t, None)


def _gerar_token(payload_bytes: bytes) -> str:
    """Token opaco baseado em hash + timestamp."""
    h = hashlib.sha256(payload_bytes + str(time.time()).encode()).hexdigest()
    return h[:32]


# ============================================================
# Erros
# ============================================================


class BeneficiarioServiceError(Exception):
    """Erro de regra de negócio do cadastro de beneficiários."""


class BeneficiarioNaoEncontradoError(BeneficiarioServiceError):
    pass


class ClienteNaoEncontradoError(BeneficiarioServiceError):
    pass


# ============================================================
# Helpers
# ============================================================


def _so_digitos(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"\D", "", str(s))


def _mask_pix(tipo: str | None, chave: str | None) -> str | None:
    if not chave:
        return None
    if tipo == "EMAIL" and "@" in chave:
        nome, dom = chave.split("@", 1)
        return f"{nome[:2]}***@{dom}"
    if tipo in ("CPF", "CNPJ"):
        digs = _so_digitos(chave)
        return f"***{digs[-4:]}" if len(digs) >= 4 else "***"
    if tipo == "TELEFONE":
        digs = _so_digitos(chave)
        return f"(**) ****-{digs[-4:]}" if len(digs) >= 4 else "***"
    # ALEATORIA / outros: mostra primeiros 4 + últimos 4
    if len(chave) > 10:
        return f"{chave[:4]}…{chave[-4:]}"
    return chave[:2] + "***"


def _normalizar_pix_tipo(tipo: str | None, chave: str | None) -> str | None:
    """Tenta classificar a chave PIX se o tipo não veio explícito."""
    if tipo:
        t = tipo.strip().upper()
        if t in ("CPF", "CNPJ", "EMAIL", "TELEFONE", "ALEATORIA", "ALEATÓRIA"):
            return "ALEATORIA" if t.startswith("ALEAT") else t
    if not chave:
        return None
    digs = _so_digitos(chave)
    if "@" in chave:
        return "EMAIL"
    if len(digs) == 11:
        return "CPF"
    if len(digs) == 14:
        return "CNPJ"
    if len(digs) in (10, 11):
        return "TELEFONE"
    return "ALEATORIA"


def _coerce_int_centavos(raw: Any) -> int | None:
    """Aceita 'R$ 1.500,00', '1500.00', '150000', etc. e devolve centavos."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    s = s.replace("R$", "").replace("r$", "").strip()
    # Se tiver vírgula, é formato BR (1.500,00)
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        valor = float(s)
    except ValueError:
        return None
    if valor < 0:
        return None
    # Se já vem como inteiro grande (provavelmente centavos), respeita
    if valor.is_integer() and valor >= 1000 and "." not in str(raw) and "," not in str(raw):
        return int(valor)
    return int(round(valor * 100))


# ============================================================
# Service
# ============================================================


@dataclass(slots=True)
class _DadosPlanilha:
    cpf_limpo: str
    nome: str
    crm: str | None
    categoria: str | None
    especialidade: str | None
    email: str | None
    telefone: str | None
    banco_codigo: str | None
    agencia: str | None
    conta: str | None
    pix_tipo: str | None
    pix_chave: str | None
    valor_padrao_centavos: int | None
    observacoes: str | None


class BeneficiarioService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ============================================================
    # CRUD
    # ============================================================

    async def _verificar_cliente(self, cliente_id: UUID) -> Cliente:
        cli = await self.db.get(Cliente, cliente_id)
        if cli is None:
            raise ClienteNaoEncontradoError(
                f"Cliente {cliente_id} não encontrado."
            )
        return cli

    async def listar(
        self,
        *,
        cliente_id: UUID | None = None,
        status: StatusBeneficiario | None = None,
        search: str | None = None,
        page: int = 1,
        per_page: int = 50,
    ) -> BeneficiarioListResponse:
        """Lista paginada com filtros."""
        page = max(1, page)
        per_page = min(max(1, per_page), 200)

        where_clauses = []
        if cliente_id:
            where_clauses.append(Beneficiario.cliente_id == cliente_id)
        if status:
            where_clauses.append(Beneficiario.status == status)
        if search:
            termo = f"%{search.strip().lower()}%"
            cpf_dig = _so_digitos(search)
            ors = [func.lower(Beneficiario.nome).like(termo)]
            if cpf_dig:
                # Busca CPF cru via hash determinístico
                ors.append(Beneficiario.cpf_hash == hash_for_lookup(cpf_dig))
                ors.append(Beneficiario.cpf_mascarado.like(f"%{cpf_dig[-2:]}%"))
            where_clauses.append(or_(*ors))

        where_expr = and_(*where_clauses) if where_clauses else None

        # Total
        q_total = select(func.count(Beneficiario.id))
        if where_expr is not None:
            q_total = q_total.where(where_expr)
        total = (await self.db.execute(q_total)).scalar_one()

        # Itens
        q = select(Beneficiario).order_by(asc(Beneficiario.nome))
        if where_expr is not None:
            q = q.where(where_expr)
        q = q.offset((page - 1) * per_page).limit(per_page)
        result = await self.db.execute(q)
        itens = list(result.scalars().all())

        return BeneficiarioListResponse(
            items=[BeneficiarioOut.model_validate(b) for b in itens],
            total=total,
            page=page,
            per_page=per_page,
            total_pages=(total + per_page - 1) // per_page,
        )

    async def buscar(self, beneficiario_id: UUID) -> Beneficiario:
        b = await self.db.get(Beneficiario, beneficiario_id)
        if b is None:
            raise BeneficiarioNaoEncontradoError(
                f"Beneficiário {beneficiario_id} não encontrado."
            )
        return b

    async def buscar_por_cpf(
        self, cliente_id: UUID, cpf_limpo: str
    ) -> Beneficiario | None:
        """Lookup determinístico via cpf_hash dentro do escopo do cliente."""
        if not cpf_limpo:
            return None
        cpf_hash = hash_for_lookup(cpf_limpo)
        q = select(Beneficiario).where(
            Beneficiario.cliente_id == cliente_id,
            Beneficiario.cpf_hash == cpf_hash,
        )
        return (await self.db.execute(q)).scalar_one_or_none()

    async def criar(
        self, payload: BeneficiarioCreateRequest
    ) -> Beneficiario:
        await self._verificar_cliente(payload.cliente_id)

        cpf_validado = validar_cpf(payload.cpf)
        if not cpf_validado.cpf_limpo or not cpf_validado.is_valido:
            raise BeneficiarioServiceError(
                f"CPF inválido: {cpf_validado.mensagem}"
            )
        cpf_limpo = cpf_validado.cpf_limpo

        # Já existe?
        existente = await self.buscar_por_cpf(payload.cliente_id, cpf_limpo)
        if existente is not None:
            raise BeneficiarioServiceError(
                f"Já existe um cadastro com este CPF para este hospital "
                f"(id={existente.id}). Use o endpoint de edição."
            )

        b = Beneficiario(
            cliente_id=payload.cliente_id,
            cpf_encrypted=encrypt(cpf_limpo),
            cpf_hash=hash_for_lookup(cpf_limpo),
            cpf_mascarado=mask_cpf(cpf_limpo),
            nome=payload.nome.strip().upper(),
            crm=payload.crm,
            categoria=payload.categoria,
            especialidade=payload.especialidade,
            email=payload.email,
            telefone=payload.telefone,
            valor_padrao_centavos=payload.valor_padrao_centavos,
            observacoes=payload.observacoes,
            status=payload.status,
            origem_cadastro=OrigemCadastroBeneficiario.MANUAL,
            ativo=payload.status == StatusBeneficiario.ATIVO,
        )
        self._aplicar_dados_bancarios(
            b,
            banco_codigo=payload.banco_codigo,
            agencia=payload.agencia,
            conta=payload.conta,
            pix_tipo=payload.pix_tipo,
            pix_chave=payload.pix_chave,
        )
        self.db.add(b)
        await self.db.flush()
        await self.db.refresh(b)
        return b

    async def atualizar(
        self,
        beneficiario_id: UUID,
        payload: BeneficiarioUpdateRequest,
    ) -> Beneficiario:
        b = await self.buscar(beneficiario_id)

        if payload.nome is not None:
            b.nome = payload.nome.strip().upper()
        for campo in (
            "crm",
            "categoria",
            "especialidade",
            "email",
            "telefone",
            "valor_padrao_centavos",
            "observacoes",
        ):
            valor = getattr(payload, campo)
            if valor is not None:
                setattr(b, campo, valor)

        # Banco / PIX só são atualizados se vieram explicitamente
        if any(
            v is not None
            for v in (
                payload.banco_codigo,
                payload.agencia,
                payload.conta,
                payload.pix_tipo,
                payload.pix_chave,
            )
        ):
            self._aplicar_dados_bancarios(
                b,
                banco_codigo=payload.banco_codigo or b.banco_codigo,
                agencia=payload.agencia,
                conta=payload.conta,
                pix_tipo=payload.pix_tipo,
                pix_chave=payload.pix_chave,
            )

        if payload.status is not None:
            b.status = payload.status
            b.ativo = payload.status == StatusBeneficiario.ATIVO

        await self.db.flush()
        await self.db.refresh(b)
        return b

    async def aprovar(self, beneficiario_id: UUID) -> Beneficiario:
        b = await self.buscar(beneficiario_id)
        b.status = StatusBeneficiario.ATIVO
        b.ativo = True
        await self.db.flush()
        await self.db.refresh(b)
        return b

    async def desativar(self, beneficiario_id: UUID) -> Beneficiario:
        b = await self.buscar(beneficiario_id)
        b.status = StatusBeneficiario.INATIVO
        b.ativo = False
        await self.db.flush()
        await self.db.refresh(b)
        return b

    # ============================================================
    # Auxiliares (criação a partir de ficha OCR / lote)
    # ============================================================

    async def upsert_de_ficha(
        self,
        cliente_id: UUID,
        *,
        cpf_limpo: str,
        nome: str,
        banco_codigo: str | None,
        agencia: str | None,
        conta: str | None,
        pix_tipo: str | None,
        pix_chave: str | None,
    ) -> tuple[Beneficiario, bool, list[str]]:
        """Garante que existe um Beneficiario para o CPF informado.

        Retorna (beneficiario, criado_agora, divergencias).

        - Se não existir → cria como PENDENTE com origem FICHA_OCR.
        - Se existir e os dados bancários divergirem → mantém o cadastro
          (cadastro é fonte de verdade) mas devolve a lista de divergências
          pra UI exibir alerta.
        """
        existente = await self.buscar_por_cpf(cliente_id, cpf_limpo)
        if existente is not None:
            divergencias = self._comparar_dados_bancarios(
                existente,
                banco_codigo=banco_codigo,
                agencia=agencia,
                conta=conta,
                pix_tipo=pix_tipo,
                pix_chave=pix_chave,
            )
            return existente, False, divergencias

        # Cria pendente
        b = Beneficiario(
            cliente_id=cliente_id,
            cpf_encrypted=encrypt(cpf_limpo),
            cpf_hash=hash_for_lookup(cpf_limpo),
            cpf_mascarado=mask_cpf(cpf_limpo),
            nome=(nome or "").strip().upper() or "PRESTADOR PENDENTE",
            status=StatusBeneficiario.PENDENTE,
            origem_cadastro=OrigemCadastroBeneficiario.FICHA_OCR,
            ativo=False,
        )
        self._aplicar_dados_bancarios(
            b,
            banco_codigo=banco_codigo,
            agencia=agencia,
            conta=conta,
            pix_tipo=pix_tipo,
            pix_chave=pix_chave,
        )
        self.db.add(b)
        await self.db.flush()
        await self.db.refresh(b)
        return b, True, []

    # ============================================================
    # Importação em massa
    # ============================================================

    async def importar_preview(
        self,
        *,
        cliente_id: UUID,
        conteudo: bytes,
        nome_arquivo: str,
    ) -> ImportPreviewResponse:
        """Lê a planilha, normaliza e devolve preview com erros + token."""
        await self._verificar_cliente(cliente_id)
        df = _ler_planilha(conteudo, nome_arquivo)
        if df.empty:
            raise BeneficiarioServiceError("Planilha sem linhas.")

        mapeamento = _detectar_mapeamento_beneficiario(list(df.columns))
        if "cpf" not in mapeamento or "nome" not in mapeamento:
            raise BeneficiarioServiceError(
                "Planilha precisa ter pelo menos as colunas 'CPF' e 'Nome'. "
                f"Colunas detectadas: {list(df.columns)}. "
                f"Aliases reconhecidos: {sorted(_ALIASES_BENEFICIARIO.keys())}."
            )

        linhas: list[LinhaImportPreview] = []
        cache_dados: list[dict[str, Any]] = []
        qtd_ok = qtd_dup = qtd_atu = qtd_err = 0

        for idx, row in df.iterrows():
            num_linha = int(idx) + 2  # +1 cabeçalho, +1 base 1
            erros: list[str] = []
            avisos: list[str] = []

            cpf_raw = str(row.get(mapeamento.get("cpf", ""), "") or "")
            nome_raw = str(row.get(mapeamento.get("nome", ""), "") or "").strip()

            cpf_validado = validar_cpf(cpf_raw)
            if not cpf_validado.cpf_limpo or not cpf_validado.is_valido:
                erros.append(
                    f"CPF inválido: {cpf_validado.mensagem or cpf_raw}"
                )
            if not nome_raw:
                erros.append("Nome vazio.")

            cpf_limpo = cpf_validado.cpf_limpo or ""
            banco_codigo = (
                str(row.get(mapeamento.get("banco", ""), "") or "").strip() or None
            )
            agencia = (
                str(row.get(mapeamento.get("agencia", ""), "") or "").strip() or None
            )
            conta = (
                str(row.get(mapeamento.get("conta", ""), "") or "").strip() or None
            )
            pix_chave = (
                str(row.get(mapeamento.get("pix_chave", ""), "") or "").strip()
                or None
            )
            pix_tipo_raw = (
                str(row.get(mapeamento.get("pix_tipo", ""), "") or "").strip()
                or None
            )
            pix_tipo = _normalizar_pix_tipo(pix_tipo_raw, pix_chave)

            valor_padrao = _coerce_int_centavos(
                row.get(mapeamento.get("valor_padrao", ""), None)
            )

            if not (banco_codigo and agencia and conta) and not pix_chave:
                avisos.append(
                    "Sem dados bancários nem PIX — prestador não poderá receber até completar."
                )

            # Lookup pra detectar duplicado/atualização
            status_linha = "OK"
            beneficiario_existente: UUID | None = None
            if cpf_limpo and not erros:
                exist = await self.buscar_por_cpf(cliente_id, cpf_limpo)
                if exist is not None:
                    beneficiario_existente = exist.id
                    if self._comparar_dados_bancarios(
                        exist,
                        banco_codigo=banco_codigo,
                        agencia=agencia,
                        conta=conta,
                        pix_tipo=pix_tipo,
                        pix_chave=pix_chave,
                    ):
                        status_linha = "ATUALIZA"
                        qtd_atu += 1
                    else:
                        status_linha = "DUPLICADO"
                        qtd_dup += 1

            if erros:
                status_linha = "ERRO"
                qtd_err += 1
            elif status_linha == "OK":
                qtd_ok += 1

            linhas.append(
                LinhaImportPreview(
                    linha_planilha=num_linha,
                    nome=nome_raw or None,
                    cpf_mascarado=mask_cpf(cpf_limpo) if cpf_limpo else None,
                    crm=(str(row.get(mapeamento.get("crm", ""), "") or "") or None),
                    email=(str(row.get(mapeamento.get("email", ""), "") or "") or None),
                    telefone=(
                        str(row.get(mapeamento.get("telefone", ""), "") or "") or None
                    ),
                    banco_codigo=banco_codigo,
                    agencia_mascarada=("****" + agencia[-4:]) if agencia and len(agencia) >= 4 else agencia,
                    conta_mascarada=mask_conta(_so_digitos(conta)) if conta else None,
                    pix_tipo=pix_tipo,
                    pix_chave_mascarada=_mask_pix(pix_tipo, pix_chave),
                    valor_padrao_centavos=valor_padrao,
                    status=status_linha,
                    erros=erros,
                    avisos=avisos,
                    beneficiario_id_existente=beneficiario_existente,
                )
            )

            cache_dados.append(
                {
                    "linha": num_linha,
                    "status": status_linha,
                    "cpf_limpo": cpf_limpo,
                    "nome": nome_raw,
                    "crm": str(row.get(mapeamento.get("crm", ""), "") or "") or None,
                    "categoria": (
                        str(row.get(mapeamento.get("categoria", ""), "") or "") or None
                    ),
                    "especialidade": (
                        str(row.get(mapeamento.get("especialidade", ""), "") or "")
                        or None
                    ),
                    "email": (
                        str(row.get(mapeamento.get("email", ""), "") or "") or None
                    ),
                    "telefone": (
                        str(row.get(mapeamento.get("telefone", ""), "") or "") or None
                    ),
                    "banco_codigo": banco_codigo,
                    "agencia": agencia,
                    "conta": conta,
                    "pix_tipo": pix_tipo,
                    "pix_chave": pix_chave,
                    "valor_padrao_centavos": valor_padrao,
                    "observacoes": (
                        str(row.get(mapeamento.get("observacoes", ""), "") or "")
                        or None
                    ),
                    "beneficiario_id_existente": (
                        str(beneficiario_existente) if beneficiario_existente else None
                    ),
                }
            )

        # Cache + token
        _gc_cache()
        token = _gerar_token(conteudo[:128] + nome_arquivo.encode())
        _PREVIEW_CACHE[token] = {
            "cliente_id": str(cliente_id),
            "linhas": cache_dados,
            "exp": time.time() + _PREVIEW_TTL_SECS,
        }

        return ImportPreviewResponse(
            cliente_id=cliente_id,
            total_linhas=len(linhas),
            qtd_ok=qtd_ok,
            qtd_duplicados=qtd_dup,
            qtd_atualiza=qtd_atu,
            qtd_erro=qtd_err,
            linhas=linhas,
            token=token,
        )

    async def importar_confirmar(
        self, payload: ImportConfirmRequest
    ) -> ImportConfirmResponse:
        _gc_cache()
        registro = _PREVIEW_CACHE.get(payload.token)
        if registro is None:
            raise BeneficiarioServiceError(
                "Token de importação inválido ou expirado. Reenvie a planilha."
            )

        cliente_id = UUID(registro["cliente_id"])
        await self._verificar_cliente(cliente_id)
        politica = (payload.politica_atualizacao or "IGNORAR").upper()
        if politica not in ("IGNORAR", "ATUALIZAR"):
            raise BeneficiarioServiceError(
                "politica_atualizacao deve ser IGNORAR ou ATUALIZAR."
            )

        criados = atualizados = ignorados = erros = 0

        for linha in registro["linhas"]:
            status_linha = linha["status"]
            if status_linha == "ERRO":
                erros += 1
                continue
            if status_linha == "DUPLICADO":
                ignorados += 1
                continue
            if status_linha == "ATUALIZA":
                if politica == "IGNORAR":
                    ignorados += 1
                    continue
                # ATUALIZAR
                bid = UUID(linha["beneficiario_id_existente"])
                b = await self.buscar(bid)
                self._aplicar_dados_bancarios(
                    b,
                    banco_codigo=linha["banco_codigo"],
                    agencia=linha["agencia"],
                    conta=linha["conta"],
                    pix_tipo=linha["pix_tipo"],
                    pix_chave=linha["pix_chave"],
                )
                if linha.get("crm"):
                    b.crm = linha["crm"]
                if linha.get("email"):
                    b.email = linha["email"]
                if linha.get("telefone"):
                    b.telefone = linha["telefone"]
                if linha.get("categoria"):
                    b.categoria = linha["categoria"]
                if linha.get("especialidade"):
                    b.especialidade = linha["especialidade"]
                if linha.get("valor_padrao_centavos") is not None:
                    b.valor_padrao_centavos = linha["valor_padrao_centavos"]
                if linha.get("observacoes"):
                    b.observacoes = linha["observacoes"]
                atualizados += 1
                continue

            # OK = criar novo
            cpf_limpo = linha["cpf_limpo"]
            b = Beneficiario(
                cliente_id=cliente_id,
                cpf_encrypted=encrypt(cpf_limpo),
                cpf_hash=hash_for_lookup(cpf_limpo),
                cpf_mascarado=mask_cpf(cpf_limpo),
                nome=(linha.get("nome") or "").strip().upper(),
                crm=linha.get("crm"),
                categoria=linha.get("categoria"),
                especialidade=linha.get("especialidade"),
                email=linha.get("email"),
                telefone=linha.get("telefone"),
                valor_padrao_centavos=linha.get("valor_padrao_centavos"),
                observacoes=linha.get("observacoes"),
                status=StatusBeneficiario.ATIVO,
                origem_cadastro=OrigemCadastroBeneficiario.PLANILHA,
                ativo=True,
            )
            self._aplicar_dados_bancarios(
                b,
                banco_codigo=linha["banco_codigo"],
                agencia=linha["agencia"],
                conta=linha["conta"],
                pix_tipo=linha["pix_tipo"],
                pix_chave=linha["pix_chave"],
            )
            self.db.add(b)
            criados += 1

        await self.db.flush()
        # Limpa o token usado
        _PREVIEW_CACHE.pop(payload.token, None)

        return ImportConfirmResponse(
            qtd_criados=criados,
            qtd_atualizados=atualizados,
            qtd_ignorados=ignorados,
            qtd_erros=erros,
        )

    # ============================================================
    # Helpers internos
    # ============================================================

    def _aplicar_dados_bancarios(
        self,
        b: Beneficiario,
        *,
        banco_codigo: str | None,
        agencia: str | None,
        conta: str | None,
        pix_tipo: str | None,
        pix_chave: str | None,
    ) -> None:
        """Atualiza os campos bancários e PIX (criptografando o que for sensível)."""
        if banco_codigo is not None:
            b.banco_codigo = (
                _so_digitos(banco_codigo)[:3] if banco_codigo else None
            )
        if agencia is not None:
            ag_limpa = _so_digitos(agencia)
            b.agencia_encrypted = encrypt(ag_limpa) if ag_limpa else None
            b.agencia_mascarada = (
                ("****" + ag_limpa[-4:]) if ag_limpa and len(ag_limpa) >= 4
                else (ag_limpa or None)
            )
        if conta is not None:
            cc_limpa = _so_digitos(conta)
            b.conta_encrypted = encrypt(cc_limpa) if cc_limpa else None
            b.conta_mascarada = mask_conta(cc_limpa) if cc_limpa else None
        if pix_tipo is not None or pix_chave is not None:
            tipo = _normalizar_pix_tipo(pix_tipo, pix_chave)
            b.pix_tipo = tipo
            if pix_chave:
                b.pix_chave_encrypted = encrypt(pix_chave)
                b.pix_chave_mascarada = _mask_pix(tipo, pix_chave)
            else:
                b.pix_chave_encrypted = None
                b.pix_chave_mascarada = None

    def _comparar_dados_bancarios(
        self,
        b: Beneficiario,
        *,
        banco_codigo: str | None,
        agencia: str | None,
        conta: str | None,
        pix_tipo: str | None,
        pix_chave: str | None,
    ) -> list[str]:
        """Detecta divergência entre cadastro e dados informados.

        NÃO descriptografa para comparar conta/agência (LGPD): compara
        as máscaras que já guardamos no cadastro, mais o banco_codigo
        e tipo PIX.
        """
        divergencias: list[str] = []

        if banco_codigo and b.banco_codigo and banco_codigo != b.banco_codigo:
            divergencias.append(
                f"Banco: cadastro={b.banco_codigo}, planilha={banco_codigo}"
            )

        if agencia:
            ag_limpa = _so_digitos(agencia)
            mascara = ("****" + ag_limpa[-4:]) if ag_limpa and len(ag_limpa) >= 4 else ag_limpa
            if b.agencia_mascarada and mascara and mascara != b.agencia_mascarada:
                divergencias.append(
                    f"Agência: cadastro={b.agencia_mascarada}, planilha={mascara}"
                )

        if conta:
            cc_limpa = _so_digitos(conta)
            if b.conta_mascarada and cc_limpa:
                mascara = mask_conta(cc_limpa)
                if mascara != b.conta_mascarada:
                    divergencias.append(
                        f"Conta: cadastro={b.conta_mascarada}, planilha={mascara}"
                    )

        if pix_tipo and b.pix_tipo and pix_tipo != b.pix_tipo:
            divergencias.append(
                f"Tipo PIX: cadastro={b.pix_tipo}, planilha={pix_tipo}"
            )

        return divergencias


__all__ = [
    "BeneficiarioNaoEncontradoError",
    "BeneficiarioService",
    "BeneficiarioServiceError",
    "ClienteNaoEncontradoError",
]
