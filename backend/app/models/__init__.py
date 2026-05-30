"""Modelos SQLAlchemy do MedPag.

Importar TODOS os models aqui para que o Alembic os descubra automaticamente.
"""

from app.models.aporte import AporteHospital, StatusAporte
from app.models.auditoria import Auditoria
from app.models.beneficiario import (
    Beneficiario,
    OrigemCadastroBeneficiario,
    StatusBeneficiario,
)
from app.models.cliente import Cliente, ModoPagamento, TipoCliente
from app.models.codigo_servico import CodigoServico
from app.models.contrato_hospital import ContratoHospital, ModoCobranca
from app.models.empresa_config import BancoEmissor, EmpresaConfig, TipoInscricao
from app.models.equipe_flex import EquipeFlex, FechamentoEquipe, MembroEquipe
from app.models.fechamento_periodo import FechamentoPeriodo, StatusFechamento
from app.models.ficha_plantao import FichaPlantao, StatusFicha
from app.models.jarvis_memoria import JarvisMemoria, TipoMemoria
from app.models.lancamento_servico import LancamentoServico, StatusLancamento
from app.models.lote import Lote, StatusLote
from app.models.pagamento import Pagamento, StatusPagamento
from app.models.plano import Plano, StatusAssinatura
from app.models.scp import (
    ApuracaoSCP,
    DistribuicaoSCP,
    ParticipanteSCP,
    RegraCota,
    StatusApuracaoSCP,
)
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
    "AporteHospital",
    "ApuracaoSCP",
    "Auditoria",
    "BancoEmissor",
    "Beneficiario",
    "Cliente",
    "CodigoServico",
    "ContratoHospital",
    "DirecaoMensagem",
    "DistribuicaoSCP",
    "EmpresaConfig",
    "EquipeFlex",
    "EventoVital",
    "FechamentoEquipe",
    "FechamentoPeriodo",
    "FichaPlantao",
    "JarvisMemoria",
    "LancamentoServico",
    "Lote",
    "MembroEquipe",
    "ModoCobranca",
    "ModoPagamento",
    "NoVital",
    "OrigemCadastroBeneficiario",
    "Pagamento",
    "ParticipanteSCP",
    "Plano",
    "RegraCota",
    "StatusAporte",
    "StatusApuracaoSCP",
    "StatusAssinatura",
    "StatusBeneficiario",
    "StatusFechamento",
    "StatusFicha",
    "StatusInstancia",
    "StatusLancamento",
    "StatusLote",
    "StatusNo",
    "StatusPagamento",
    "TipoAmbiente",
    "TipoCliente",
    "TipoEvento",
    "TipoInscricao",
    "TipoMemoria",
    "TipoSensor",
    "User",
    "UserRole",
    "WhatsAppInstancia",
    "WhatsAppMensagem",
    "WhatsAppUser",
]
