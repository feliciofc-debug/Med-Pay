"""Modelos SQLAlchemy do MedPag.

Importar TODOS os models aqui para que o Alembic os descubra automaticamente.
"""

from app.models.auditoria import Auditoria
from app.models.beneficiario import Beneficiario
from app.models.cliente import Cliente
from app.models.contrato_hospital import ContratoHospital, ModoCobranca
from app.models.empresa_config import EmpresaConfig, TipoInscricao
from app.models.equipe_flex import EquipeFlex, FechamentoEquipe, MembroEquipe
from app.models.ficha_plantao import FichaPlantao, StatusFicha
from app.models.lote import Lote, StatusLote
from app.models.pagamento import Pagamento, StatusPagamento
from app.models.user import User, UserRole
from app.models.whatsapp import (
    DirecaoMensagem,
    StatusInstancia,
    WhatsAppInstancia,
    WhatsAppMensagem,
    WhatsAppUser,
)

__all__ = [
    "Auditoria",
    "Beneficiario",
    "Cliente",
    "ContratoHospital",
    "DirecaoMensagem",
    "EmpresaConfig",
    "EquipeFlex",
    "FechamentoEquipe",
    "FichaPlantao",
    "Lote",
    "MembroEquipe",
    "ModoCobranca",
    "Pagamento",
    "StatusFicha",
    "StatusInstancia",
    "StatusLote",
    "StatusPagamento",
    "TipoInscricao",
    "User",
    "UserRole",
    "WhatsAppInstancia",
    "WhatsAppMensagem",
    "WhatsAppUser",
]
