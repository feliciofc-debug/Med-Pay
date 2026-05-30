import { Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "@/hooks/useAuth";
import { Layout } from "@/components/Layout";
import { LandingPage } from "@/pages/LandingPage";
import { LoginPage } from "@/pages/LoginPage";
import { SignupPage } from "@/pages/SignupPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { DashboardExecutivoPage } from "@/pages/DashboardExecutivoPage";
import { MedicoHomePage } from "@/pages/MedicoHomePage";
import { MedicoExtratoPage } from "@/pages/MedicoExtratoPage";
import { FechamentoPeriodoPage } from "@/pages/FechamentoPeriodoPage";
import { FluxoOperacaoPage } from "@/pages/FluxoOperacaoPage";
import { ContratosPage } from "@/pages/ContratosPage";
import { UploadPage } from "@/pages/UploadPage";
import { LoteDetalhePage } from "@/pages/LoteDetalhePage";
import { LotesListPage } from "@/pages/LotesListPage";
import { FichasListPage } from "@/pages/FichasListPage";
import { FichaDetalhePage } from "@/pages/FichaDetalhePage";
import { EquipesPage } from "@/pages/EquipesPage";
import { EquipeDetalhePage } from "@/pages/EquipeDetalhePage";
import { PrestadoresPage } from "@/pages/PrestadoresPage";
import { MeuPainelCoordenadorPage } from "@/pages/MeuPainelCoordenadorPage";
import { AdminUsuariosPage } from "@/pages/AdminUsuariosPage";
import { AdminRelatorioErrosPage } from "@/pages/AdminRelatorioErrosPage";
import { AdminDevolucoesPage } from "@/pages/AdminDevolucoesPage";
import { AdminEmpresaPagadoraPage } from "@/pages/AdminEmpresaPagadoraPage";
import { AdminWhatsAppPage } from "@/pages/AdminWhatsAppPage";
import { AdminPlanosPage } from "@/pages/AdminPlanosPage";
import { AdminAuditoriaPage } from "@/pages/AdminAuditoriaPage";
import { ConfigurarOperacaoPage } from "@/pages/ConfigurarOperacaoPage";
import { ExtratoConsolidadoPage } from "@/pages/ExtratoConsolidadoPage";
import { SuperAdminPage } from "@/pages/SuperAdminPage";
import { AnestesistaLancarPage } from "@/pages/AnestesistaLancarPage";
import { AnestesistaMeusLancamentosPage } from "@/pages/AnestesistaMeusLancamentosPage";
import { CrmLandingPage } from "@/pages/CrmLandingPage";
import { VitalDashboardPage } from "@/pages/VitalDashboardPage";
import { ScpPage } from "@/pages/ScpPage";
import { ContasRepassePage } from "@/pages/ContasRepassePage";
import { CarteiraPage } from "@/pages/CarteiraPage";
import type { UserRole } from "@/types";

// Pra qual rota mandar o usuário quando ele cai em alguma sem permissão.
// Cada papel tem uma "casa" — o lugar onde ele opera no dia-a-dia.
function rotaInicial(role: UserRole | undefined): string {
  if (role === "MEDICO") return "/app/medico";
  if (role === "COORDENADOR") return "/app/coordenador";
  if (role === "FINANCEIRO") return "/app/lotes";
  if (role === "OPERADOR") return "/app/upload";
  // ADMIN, APROVADOR, GESTOR → dashboard executivo
  return "/app";
}

function ProtectedRoute({
  children,
  roles,
}: {
  children: React.ReactNode;
  roles?: UserRole[];
}) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-slate-500">
        Carregando...
      </div>
    );
  }
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  if (roles && !roles.includes(user.role)) {
    return <Navigate to={rotaInicial(user.role)} replace />;
  }
  return <Layout>{children}</Layout>;
}

function AdminRoute({ children }: { children: React.ReactNode }) {
  return <ProtectedRoute roles={["ADMIN"]}>{children}</ProtectedRoute>;
}

export default function App() {
  return (
    <Routes>
      {/* Público */}
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      {/* Landing universal de médicos (entrada por CRM) */}
      <Route path="/crm" element={<CrmLandingPage />} />

      {/* Área do médico (sessão leve por CRM, sem User no sistema) */}
      <Route path="/anestesista" element={<AnestesistaLancarPage />} />
      <Route
        path="/anestesista/meus-lancamentos"
        element={<AnestesistaMeusLancamentosPage />}
      />

      {/* Área autenticada */}
      <Route
        path="/app"
        element={
          <ProtectedRoute roles={["ADMIN", "APROVADOR", "GESTOR"]}>
            <DashboardPage />
          </ProtectedRoute>
        }
      />
      {/* Mapa visual do fluxo da operação — acessível a TODOS os papéis logados */}
      <Route
        path="/app/fluxo"
        element={
          <ProtectedRoute>
            <FluxoOperacaoPage />
          </ProtectedRoute>
        }
      />
      {/* Fechamento de período */}
      <Route
        path="/app/fechamento"
        element={
          <ProtectedRoute
            roles={["ADMIN", "APROVADOR", "GESTOR", "FINANCEIRO"]}
          >
            <FechamentoPeriodoPage />
          </ProtectedRoute>
        }
      />
      {/* App do médico — placeholder pra Leva 3.1 */}
      <Route
        path="/app/medico"
        element={
          <ProtectedRoute roles={["MEDICO", "ADMIN"]}>
            <MedicoHomePage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/medico/extrato"
        element={
          <ProtectedRoute roles={["MEDICO", "ADMIN"]}>
            <MedicoExtratoPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/executivo"
        element={
          <ProtectedRoute roles={["ADMIN"]}>
            <DashboardExecutivoPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/contratos"
        element={
          <ProtectedRoute roles={["ADMIN"]}>
            <ContratosPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/upload"
        element={
          <ProtectedRoute>
            <UploadPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/lotes"
        element={
          <ProtectedRoute>
            <LotesListPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/lotes/:id"
        element={
          <ProtectedRoute>
            <LoteDetalhePage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/fichas"
        element={
          <ProtectedRoute>
            <FichasListPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/fichas/:id"
        element={
          <ProtectedRoute>
            <FichaDetalhePage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/extrato-consolidado"
        element={
          <ProtectedRoute roles={["ADMIN", "APROVADOR"]}>
            <ExtratoConsolidadoPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/prestadores"
        element={
          <ProtectedRoute roles={["ADMIN", "APROVADOR", "OPERADOR"]}>
            <PrestadoresPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/equipes"
        element={
          <ProtectedRoute roles={["ADMIN", "APROVADOR", "OPERADOR"]}>
            <EquipesPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/equipes/:id"
        element={
          <ProtectedRoute roles={["ADMIN", "APROVADOR", "OPERADOR"]}>
            <EquipeDetalhePage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/coordenador"
        element={
          <ProtectedRoute roles={["COORDENADOR", "ADMIN", "APROVADOR", "OPERADOR"]}>
            <MeuPainelCoordenadorPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/vital"
        element={
          <ProtectedRoute roles={["ADMIN", "APROVADOR", "OPERADOR"]}>
            <VitalDashboardPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/scp"
        element={
          <ProtectedRoute roles={["ADMIN", "GESTOR"]}>
            <ScpPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/contas-repasse"
        element={
          <ProtectedRoute roles={["ADMIN", "GESTOR"]}>
            <ContasRepassePage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/app/carteira"
        element={
          <ProtectedRoute roles={["ADMIN", "GESTOR"]}>
            <CarteiraPage />
          </ProtectedRoute>
        }
      />

      {/* Área Admin (gestão do BPO) — restrita a role=ADMIN */}
      <Route
        path="/app/admin/usuarios"
        element={
          <AdminRoute>
            <AdminUsuariosPage />
          </AdminRoute>
        }
      />
      <Route
        path="/app/admin/relatorio-erros"
        element={
          <AdminRoute>
            <AdminRelatorioErrosPage />
          </AdminRoute>
        }
      />
      <Route
        path="/app/admin/devolucoes"
        element={
          <AdminRoute>
            <AdminDevolucoesPage />
          </AdminRoute>
        }
      />
      <Route
        path="/app/admin/empresa-pagadora"
        element={
          <AdminRoute>
            <AdminEmpresaPagadoraPage />
          </AdminRoute>
        }
      />
      <Route
        path="/app/admin/whatsapp"
        element={
          <AdminRoute>
            <AdminWhatsAppPage />
          </AdminRoute>
        }
      />
      <Route
        path="/app/admin/planos"
        element={
          <AdminRoute>
            <AdminPlanosPage />
          </AdminRoute>
        }
      />
      <Route
        path="/app/super-admin"
        element={
          <AdminRoute>
            <SuperAdminPage />
          </AdminRoute>
        }
      />
      <Route
        path="/app/admin/auditoria"
        element={
          <AdminRoute>
            <AdminAuditoriaPage />
          </AdminRoute>
        }
      />
      <Route
        path="/app/admin/operacao"
        element={
          <AdminRoute>
            <ConfigurarOperacaoPage />
          </AdminRoute>
        }
      />

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
