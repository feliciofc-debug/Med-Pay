"""Service do módulo MedPag Vital.

Responsabilidades:
    - CRUD de ambientes e nós
    - Geração de api_key segura
    - Ingestão de eventos com autenticação por header
    - Atualização do estado do nó (last_seen, status, RSSI)
    - Consulta paginada de eventos
    - Auditoria cruzada entre LancamentoServico e EventoVital
    - Estatísticas agregadas pro dashboard

Convenção: toda exceção de negócio sobe como `MedPagException`. Nada de
ValueError direto.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import MedPagException
from app.models.cliente import Cliente
from app.models.lancamento_servico import LancamentoServico
from app.models.vital import (
    AmbienteMonitorado,
    EventoVital,
    NoVital,
    StatusNo,
    TipoAmbiente,
    TipoEvento,
    TipoSensor,
)
from app.schemas.vital import (
    AuditoriaResumo,
    EventoFiltro,
    EventoIngest,
    EventoIngestLote,
    IngestResult,
    VitalStats,
)


# ============================================================
# Exceções específicas
# ============================================================


class AmbienteVitalNaoEncontradoError(MedPagException):
    code = "VITAL_AMBIENTE_NAO_ENCONTRADO"
    status_code = 404


class NoVitalNaoEncontradoError(MedPagException):
    code = "VITAL_NO_NAO_ENCONTRADO"
    status_code = 404


class ApiKeyVitalInvalidaError(MedPagException):
    code = "VITAL_API_KEY_INVALIDA"
    status_code = 401


class NoInativoError(MedPagException):
    code = "VITAL_NO_INATIVO"
    status_code = 403


class LancamentoNaoEncontradoError(MedPagException):
    code = "VITAL_LANCAMENTO_NAO_ENCONTRADO"
    status_code = 404


# ============================================================
# Constantes de regra de negócio
# ============================================================

# Após N segundos sem heartbeat, marcamos o nó como OFFLINE.
LIMITE_OFFLINE_S = 120

# Janela default da auditoria cruzada com lançamento, quando não há
# horário explícito (lançamento só tem data, não hora).
JANELA_AUDITORIA_HORAS = 4


# ============================================================
# Service principal
# ============================================================


class VitalService:
    """Camada de orquestração do módulo Vital."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # --------------------------------------------------------
    # Ambientes
    # --------------------------------------------------------

    async def criar_ambiente(
        self,
        *,
        cliente_id: UUID,
        nome: str,
        tipo: TipoAmbiente,
        descricao: str | None = None,
        referencia_externa: str | None = None,
    ) -> AmbienteMonitorado:
        """Cria um ambiente monitorado pra um cliente."""
        await self._garante_cliente(cliente_id)

        amb = AmbienteMonitorado(
            cliente_id=cliente_id,
            nome=nome.strip(),
            tipo=tipo,
            descricao=descricao,
            referencia_externa=referencia_externa,
        )
        self.db.add(amb)
        await self.db.flush()
        await self.db.refresh(amb)
        return amb

    async def listar_ambientes(
        self, *, cliente_id: UUID, somente_ativos: bool = True
    ) -> list[AmbienteMonitorado]:
        stmt = select(AmbienteMonitorado).where(
            AmbienteMonitorado.cliente_id == cliente_id
        )
        if somente_ativos:
            stmt = stmt.where(AmbienteMonitorado.ativo.is_(True))
        stmt = stmt.order_by(AmbienteMonitorado.nome.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def atualizar_ambiente(
        self, *, ambiente_id: UUID, **campos: object
    ) -> AmbienteMonitorado:
        amb = await self.db.get(AmbienteMonitorado, ambiente_id)
        if amb is None:
            raise AmbienteVitalNaoEncontradoError("Ambiente não encontrado")

        for k, v in campos.items():
            if v is not None and hasattr(amb, k):
                setattr(amb, k, v)

        await self.db.flush()
        await self.db.refresh(amb)
        return amb

    # --------------------------------------------------------
    # Nós (sensores)
    # --------------------------------------------------------

    async def criar_no(
        self,
        *,
        cliente_id: UUID,
        node_id: str,
        tipo: TipoSensor,
        apelido: str | None = None,
        ambiente_id: UUID | None = None,
        privacy_mode: bool = False,
    ) -> tuple[NoVital, str]:
        """Registra um sensor físico e devolve a api_key gerada."""
        await self._garante_cliente(cliente_id)

        if ambiente_id is not None:
            amb = await self.db.get(AmbienteMonitorado, ambiente_id)
            if amb is None or amb.cliente_id != cliente_id:
                raise AmbienteVitalNaoEncontradoError(
                    "Ambiente não pertence a este cliente"
                )

        # 48 chars de entropia — suficiente pra IoT, não tem refresh token aqui.
        api_key = "vital_" + secrets.token_urlsafe(36)

        no = NoVital(
            cliente_id=cliente_id,
            ambiente_id=ambiente_id,
            node_id=node_id.strip(),
            tipo=tipo,
            apelido=apelido,
            api_key=api_key,
            status=StatusNo.NUNCA_VISTO,
            privacy_mode=privacy_mode,
        )
        self.db.add(no)
        await self.db.flush()
        await self.db.refresh(no)
        return no, api_key

    async def listar_nos(
        self, *, cliente_id: UUID, somente_ativos: bool = True
    ) -> list[NoVital]:
        # Atualiza status OFFLINE de quem passou do limite sem heartbeat antes
        # de listar (cheap: 1 UPDATE).
        await self._marcar_nos_offline(cliente_id)

        stmt = select(NoVital).where(NoVital.cliente_id == cliente_id)
        if somente_ativos:
            stmt = stmt.where(NoVital.ativo.is_(True))
        stmt = stmt.order_by(NoVital.apelido.asc().nulls_last(), NoVital.node_id.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def atualizar_no(self, *, no_id: UUID, **campos: object) -> NoVital:
        no = await self.db.get(NoVital, no_id)
        if no is None:
            raise NoVitalNaoEncontradoError("Nó não encontrado")

        for k, v in campos.items():
            if v is not None and hasattr(no, k):
                setattr(no, k, v)

        await self.db.flush()
        await self.db.refresh(no)
        return no

    async def regenerar_api_key(self, *, no_id: UUID) -> tuple[NoVital, str]:
        """Rotaciona o api_key do nó. Use em caso de comprometimento."""
        no = await self.db.get(NoVital, no_id)
        if no is None:
            raise NoVitalNaoEncontradoError("Nó não encontrado")
        nova = "vital_" + secrets.token_urlsafe(36)
        no.api_key = nova
        await self.db.flush()
        await self.db.refresh(no)
        return no, nova

    async def _marcar_nos_offline(self, cliente_id: UUID) -> None:
        """Marca como OFFLINE quem ficou > LIMITE_OFFLINE_S sem heartbeat."""
        limite = datetime.now(tz=timezone.utc) - timedelta(seconds=LIMITE_OFFLINE_S)
        stmt = (
            update(NoVital)
            .where(
                NoVital.cliente_id == cliente_id,
                NoVital.status == StatusNo.ONLINE,
                NoVital.last_seen_at.is_not(None),
                NoVital.last_seen_at < limite,
            )
            .values(status=StatusNo.OFFLINE)
        )
        await self.db.execute(stmt)

    # --------------------------------------------------------
    # Ingestão de eventos
    # --------------------------------------------------------

    async def autenticar_no_por_api_key(self, api_key: str) -> NoVital:
        """Resolve o NoVital pelo api_key — base de toda ingestão."""
        if not api_key or len(api_key) < 16:
            raise ApiKeyVitalInvalidaError("API key ausente ou malformada")

        result = await self.db.execute(
            select(NoVital).where(NoVital.api_key == api_key)
        )
        no = result.scalar_one_or_none()
        if no is None:
            raise ApiKeyVitalInvalidaError("API key não reconhecida")
        if not no.ativo:
            raise NoInativoError("Nó desativado — contate o administrador")
        return no

    async def ingerir_evento(
        self,
        *,
        no: NoVital,
        evento: EventoIngest,
    ) -> EventoVital:
        """Grava um evento individual e atualiza o heartbeat do nó."""
        agora = datetime.now(tz=timezone.utc)
        observado = evento.observado_em or agora

        # Bloqueio LGPD: nó em privacy_mode não pode enviar HR/BR brutos.
        if no.privacy_mode and evento.tipo in (
            TipoEvento.BATIMENTO_CARDIACO,
            TipoEvento.FREQUENCIA_RESPIRATORIA,
        ):
            raise MedPagException(
                "Nó está em privacy_mode — dados biométricos brutos não são aceitos",
                code="VITAL_PRIVACY_VIOLATION",
                status_code=403,
            )

        ev = EventoVital(
            cliente_id=no.cliente_id,
            ambiente_id=no.ambiente_id,
            no_id=no.id,
            tipo=evento.tipo,
            valor_num=evento.valor_num,
            valor_texto=evento.valor_texto,
            confianca=evento.confianca,
            observado_em=observado,
            extras_json=evento.extras_json,
        )
        self.db.add(ev)

        no.last_seen_at = agora
        no.status = StatusNo.ONLINE
        if evento.rssi is not None:
            no.last_rssi = evento.rssi
        if evento.firmware_version:
            no.firmware_version = evento.firmware_version

        await self.db.flush()
        return ev

    async def ingerir_lote(
        self, *, no: NoVital, lote: EventoIngestLote
    ) -> IngestResult:
        """Ingestão em batch — modo otimizado pro ESP32."""
        aceitos = 0
        rejeitados = 0
        erros: list[str] = []

        agora = datetime.now(tz=timezone.utc)
        max_obs = agora

        for ev in lote.eventos:
            try:
                if no.privacy_mode and ev.tipo in (
                    TipoEvento.BATIMENTO_CARDIACO,
                    TipoEvento.FREQUENCIA_RESPIRATORIA,
                ):
                    rejeitados += 1
                    erros.append(f"{ev.tipo.value}: bloqueado por privacy_mode")
                    continue

                observado = ev.observado_em or agora
                if observado > max_obs:
                    max_obs = observado

                self.db.add(
                    EventoVital(
                        cliente_id=no.cliente_id,
                        ambiente_id=no.ambiente_id,
                        no_id=no.id,
                        tipo=ev.tipo,
                        valor_num=ev.valor_num,
                        valor_texto=ev.valor_texto,
                        confianca=ev.confianca,
                        observado_em=observado,
                        extras_json=ev.extras_json,
                    )
                )
                aceitos += 1
            except Exception as exc:  # noqa: BLE001 — registra mas não derruba o batch
                rejeitados += 1
                erros.append(f"{ev.tipo.value}: {type(exc).__name__}")

        # Atualiza heartbeat
        no.last_seen_at = agora
        no.status = StatusNo.ONLINE
        if lote.rssi is not None:
            no.last_rssi = lote.rssi
        if lote.firmware_version:
            no.firmware_version = lote.firmware_version

        await self.db.flush()
        return IngestResult(aceitos=aceitos, rejeitados=rejeitados, erros=erros[:20])

    # --------------------------------------------------------
    # Consulta de eventos
    # --------------------------------------------------------

    async def listar_eventos(
        self, *, filtro: EventoFiltro
    ) -> tuple[list[EventoVital], int]:
        """Listagem paginada com filtros."""
        conds = []
        if filtro.cliente_id is not None:
            conds.append(EventoVital.cliente_id == filtro.cliente_id)
        if filtro.ambiente_id is not None:
            conds.append(EventoVital.ambiente_id == filtro.ambiente_id)
        if filtro.no_id is not None:
            conds.append(EventoVital.no_id == filtro.no_id)
        if filtro.tipo is not None:
            conds.append(EventoVital.tipo == filtro.tipo)
        if filtro.de is not None:
            conds.append(EventoVital.observado_em >= filtro.de)
        if filtro.ate is not None:
            conds.append(EventoVital.observado_em <= filtro.ate)
        if filtro.data is not None:
            ini = datetime.combine(filtro.data, datetime.min.time(), tzinfo=timezone.utc)
            fim = ini + timedelta(days=1)
            conds.append(EventoVital.observado_em >= ini)
            conds.append(EventoVital.observado_em < fim)

        where_clause = and_(*conds) if conds else None

        # Total
        count_stmt = select(func.count(EventoVital.id))
        if where_clause is not None:
            count_stmt = count_stmt.where(where_clause)
        total = (await self.db.execute(count_stmt)).scalar_one()

        # Página
        stmt = select(EventoVital)
        if where_clause is not None:
            stmt = stmt.where(where_clause)
        stmt = (
            stmt.order_by(EventoVital.observado_em.desc())
            .limit(filtro.limite)
            .offset(filtro.offset)
        )
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
        return items, int(total)

    # --------------------------------------------------------
    # Stats agregadas
    # --------------------------------------------------------

    async def stats_dashboard(self, *, cliente_id: UUID) -> VitalStats:
        """Resumo executivo do módulo Vital."""
        await self._marcar_nos_offline(cliente_id)

        nos = await self.listar_nos(cliente_id=cliente_id, somente_ativos=False)
        nos_total = len(nos)
        nos_online = sum(1 for n in nos if n.status == StatusNo.ONLINE)
        nos_offline = nos_total - nos_online

        amb_count = (
            await self.db.execute(
                select(func.count(AmbienteMonitorado.id)).where(
                    AmbienteMonitorado.cliente_id == cliente_id,
                    AmbienteMonitorado.ativo.is_(True),
                )
            )
        ).scalar_one()

        ultimas_24h = datetime.now(tz=timezone.utc) - timedelta(hours=24)

        eventos_24h = (
            await self.db.execute(
                select(func.count(EventoVital.id)).where(
                    EventoVital.cliente_id == cliente_id,
                    EventoVital.observado_em >= ultimas_24h,
                )
            )
        ).scalar_one()

        quedas_24h = (
            await self.db.execute(
                select(func.count(EventoVital.id)).where(
                    EventoVital.cliente_id == cliente_id,
                    EventoVital.observado_em >= ultimas_24h,
                    EventoVital.tipo == TipoEvento.QUEDA,
                )
            )
        ).scalar_one()

        distress_24h = (
            await self.db.execute(
                select(func.count(EventoVital.id)).where(
                    EventoVital.cliente_id == cliente_id,
                    EventoVital.observado_em >= ultimas_24h,
                    EventoVital.tipo == TipoEvento.POSSIVEL_DISTRESS,
                )
            )
        ).scalar_one()

        ultima_atividade = (
            await self.db.execute(
                select(func.max(EventoVital.observado_em)).where(
                    EventoVital.cliente_id == cliente_id
                )
            )
        ).scalar_one()

        return VitalStats(
            cliente_id=cliente_id,
            nos_total=nos_total,
            nos_online=nos_online,
            nos_offline=nos_offline,
            ambientes_total=int(amb_count),
            eventos_24h=int(eventos_24h),
            quedas_24h=int(quedas_24h),
            distress_24h=int(distress_24h),
            ultima_atividade=ultima_atividade,
        )

    # --------------------------------------------------------
    # Auditoria de lançamento × Vital
    # --------------------------------------------------------

    async def auditar_lancamento(
        self,
        *,
        lancamento_id: UUID,
        ambiente_id: UUID | None = None,
        inicio: datetime | None = None,
        fim: datetime | None = None,
    ) -> AuditoriaResumo:
        """Cruza um lançamento médico com eventos Vital do mesmo período.

        Estratégia:
            1. Pega o lançamento + cliente.
            2. Determina janela temporal: usa (inicio, fim) explícitos OU
               assume "data_servico ± JANELA_AUDITORIA_HORAS/2" como fallback.
            3. Determina ambiente: usa explícito OU tenta inferir pelo
               campo `hospital_local` (futuro: lookup mais robusto).
            4. Agrega eventos da janela e devolve veredito + motivos.
        """
        lanc = await self.db.get(LancamentoServico, lancamento_id)
        if lanc is None:
            raise LancamentoNaoEncontradoError("Lançamento não encontrado")

        # Janela temporal
        if inicio is None or fim is None:
            data = datetime.combine(
                lanc.data_servico, datetime.min.time(), tzinfo=timezone.utc
            )
            inicio = data
            fim = data + timedelta(hours=24)

        duracao_minutos = max(1, int((fim - inicio).total_seconds() / 60))

        ambiente: AmbienteMonitorado | None = None
        if ambiente_id is not None:
            ambiente = await self.db.get(AmbienteMonitorado, ambiente_id)

        # Query base de eventos
        conds = [
            EventoVital.cliente_id == lanc.cliente_id,
            EventoVital.observado_em >= inicio,
            EventoVital.observado_em <= fim,
        ]
        if ambiente is not None:
            conds.append(EventoVital.ambiente_id == ambiente.id)

        stmt = select(EventoVital).where(and_(*conds))
        result = await self.db.execute(stmt)
        eventos = list(result.scalars().all())

        # Agregações
        total = len(eventos)
        presenca = any(
            ev.tipo == TipoEvento.PRESENCA and (ev.valor_num or 0) > 0
            for ev in eventos
        )
        contagens = [
            int(ev.valor_num or 0)
            for ev in eventos
            if ev.tipo == TipoEvento.CONTAGEM_PESSOAS and ev.valor_num is not None
        ]
        contagem_max = max(contagens) if contagens else None
        contagem_media = (sum(contagens) / len(contagens)) if contagens else None

        quedas = sum(1 for ev in eventos if ev.tipo == TipoEvento.QUEDA)
        distress = sum(1 for ev in eventos if ev.tipo == TipoEvento.POSSIVEL_DISTRESS)

        bpm = [
            ev.valor_num
            for ev in eventos
            if ev.tipo == TipoEvento.BATIMENTO_CARDIACO and ev.valor_num is not None
        ]
        rpm = [
            ev.valor_num
            for ev in eventos
            if ev.tipo == TipoEvento.FREQUENCIA_RESPIRATORIA and ev.valor_num is not None
        ]
        bpm_medio = (sum(bpm) / len(bpm)) if bpm else None
        rpm_medio = (sum(rpm) / len(rpm)) if rpm else None

        # Estimativa de "paciente deitado" via POSE
        pose_eventos = [
            ev for ev in eventos
            if ev.tipo == TipoEvento.POSE and ev.valor_texto
        ]
        deitado = sum(1 for ev in pose_eventos if ev.valor_texto == "DEITADO")
        paciente_deitado_pct = (
            (deitado / len(pose_eventos)) if pose_eventos else None
        )

        # Heurística do veredito
        motivos: list[str] = []
        veredito = "VALIDO"

        if total == 0:
            veredito = "INSUFICIENTE"
            motivos.append(
                "Nenhum evento Vital no período — sensor não instalado ou offline."
            )
        else:
            if not presenca and contagem_max is None:
                veredito = "AUDITORIA"
                motivos.append("Nenhum sinal de presença no ambiente durante a janela.")
            if contagem_max is not None and contagem_max < 2:
                motivos.append(
                    f"Contagem máxima de {contagem_max} pessoa — incompatível com "
                    "procedimento que normalmente envolve médico + paciente."
                )
                if veredito == "VALIDO":
                    veredito = "AUDITORIA"
            if quedas > 0:
                motivos.append(f"{quedas} queda(s) detectada(s) no período.")
            if distress > 0:
                motivos.append(
                    f"{distress} sinais de distress fisiológico — revisar prontuário."
                )
            if paciente_deitado_pct is not None and paciente_deitado_pct < 0.3:
                motivos.append(
                    "Paciente esteve deitado por menos de 30% do tempo — "
                    "incompatível com cirurgia."
                )
                if veredito == "VALIDO":
                    veredito = "AUDITORIA"

        if veredito == "VALIDO" and not motivos:
            motivos.append("Sinais Vital compatíveis com o procedimento lançado.")

        return AuditoriaResumo(
            lancamento_id=lanc.id,
            ambiente_id=ambiente.id if ambiente else None,
            ambiente_nome=ambiente.nome if ambiente else None,
            inicio=inicio,
            fim=fim,
            duracao_minutos=duracao_minutos,
            total_eventos=total,
            presenca_detectada=presenca,
            contagem_pessoas_max=contagem_max,
            contagem_pessoas_media=contagem_media,
            quedas_detectadas=quedas,
            distress_detectado=distress,
            paciente_deitado_pct=paciente_deitado_pct,
            bpm_medio=bpm_medio,
            rpm_medio=rpm_medio,
            veredito=veredito,
            motivos=motivos,
        )

    # --------------------------------------------------------
    # Helpers
    # --------------------------------------------------------

    async def _garante_cliente(self, cliente_id: UUID) -> Cliente:
        cli = await self.db.get(Cliente, cliente_id)
        if cli is None:
            raise MedPagException(
                "Cliente não encontrado", code="CLIENTE_NAO_ENCONTRADO", status_code=404
            )
        return cli


__all__ = [
    "AmbienteVitalNaoEncontradoError",
    "ApiKeyVitalInvalidaError",
    "LancamentoNaoEncontradoError",
    "NoInativoError",
    "NoVitalNaoEncontradoError",
    "VitalService",
]
