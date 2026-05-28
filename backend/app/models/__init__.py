"""Modelos SQLAlchemy do MedPag.

Importar TODOS os models aqui para que o Alembic os descubra automaticamente.
"""

from app.models.auditoria import Auditoria
from app.models.beneficiario import (
    Beneficiario,
    OrigemCadastroBeneficiario,
    StatusBeneficiario,
)
from app.models.cliente import Cliente
from app.models.codigo_servico import CodigoServico
from app.models.contrato_hospital import ContratoHospital, ModoCobranca
from app.models.empresa_config import BancoEmissor, EmpresaConfig, TipoInscricao
from app.models.equipe_flex import EquipeFlex, FechamentoEquipe, MembroEquipe
from app.models.ficha_plantao import FichaPlantao, StatusFicha
from app.models.lancamento_servico import LancamentoServico, StatusLancamento
from app.models.lote import Lote, StatusLote
from app.models.pagamento import Pagamento, StatusPagamento
from app.models.plano import Plano, StatusAssinatura
from app.models.user import User, UserRole
from app.models.vital import (
    AmbienteMonitorado,
    EventoVital,
    NoVital,
    StatusNo,
    TipoAmbiente,
    TipoEvento,
    TipoSensor,
)
from app.models.whatsapp import (
    DirecaoMensagem,
    StatusInstancia,
    WhatsAppInstancia,
    WhatsAppMensagem,
    WhatsAppUser,
)

__all__ = [
    "AmbienteMonitorado",
    "Auditoria",
    "BancoEmissor",
    "Beneficiario",
    "Cliente",
    "CodigoServico",
    "ContratoHospital",
    "DirecaoMensagem",
    "EmpresaConfig",
    "EquipeFlex",
    "EventoVital",
    "FechamentoEquipe",
    "FichaPlantao",
    "LancamentoServico",
    "Lote",
    "MembroEquipe",
    "ModoCobranca",
    "NoVital",
    "OrigemCadastroBeneficiario",
    "Pagamento",
    "Plano",
    "StatusAssinatura",
    "StatusBeneficiario",
    "StatusFicha",
    "StatusInstancia",
    "StatusLancamento",
    "StatusLote",
    "StatusNo",
    "StatusPagamento",
    "TipoAmbiente",
    "TipoEvento",
    "TipoInscricao",
    "TipoSensor",
    "User",
    "UserRole",
    "WhatsAppInstancia",
    "WhatsAppMensagem",
    "WhatsAppUser",
]
