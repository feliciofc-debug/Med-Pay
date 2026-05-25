// Tipos compartilhados — espelham os schemas Pydantic do backend.

export type UserRole = "ADMIN" | "APROVADOR" | "OPERADOR" | "COORDENADOR";

// ============================================================
// Equipe Flex (banco de horas compartilhado)
// ============================================================

export type ModoCobranca = "PERCENTUAL_REPASSE" | "MENSALIDADE_SAAS";

export interface MembroEquipe {
  id: string;
  nome: string;
  cpf: string;
  crm_ou_registro: string | null;
  chave_pix: string | null;
  banco_codigo: string | null;
  agencia: string | null;
  conta: string | null;
  ativo: boolean;
}

export interface MembroEquipePayload {
  nome: string;
  cpf: string;
  crm_ou_registro?: string | null;
  chave_pix?: string | null;
  banco_codigo?: string | null;
  agencia?: string | null;
  conta?: string | null;
  ativo?: boolean;
}

export interface EquipeFlex {
  id: string;
  cliente: { id: string; nome: string; cnpj: string | null };
  nome: string;
  categoria: string;
  valor_hora_centavos: number;
  ativa: boolean;
  observacoes: string | null;
  qtd_membros: number;
  qtd_membros_ativos: number;
  membros: MembroEquipe[];
  created_at: string;
}

export interface EquipePayload {
  cliente_id: string;
  nome: string;
  categoria: string;
  valor_hora_centavos: number;
  ativa: boolean;
  observacoes?: string | null;
}

export interface FechamentoEquipePayload {
  equipe_id: string;
  competencia: string; // "YYYY-MM"
  horas_total: number;
  origem?: "DIGITACAO" | "FICHA_OCR";
  ficha_id?: string | null;
  confirmar?: boolean;
  observacoes?: string | null;
}

export interface FechamentoEquipe {
  id: string | null;
  equipe_id: string;
  competencia: string;
  horas_total: number;
  valor_hora_centavos: number;
  valor_bruto_centavos: number;
  desconto_medpag_centavos: number;
  valor_liquido_centavos: number;
  qtd_membros: number;
  valor_por_membro_centavos: number;
  origem: string;
  ficha_id: string | null;
  lote_id: string | null;
  aprovado_at: string | null;
  observacoes: string | null;
  created_at: string | null;
}

export interface User {
  id: string;
  email: string;
  nome: string;
  role: UserRole;
  ativo: boolean;
  created_at: string;
  last_login_at: string | null;
}

export type StatusLote =
  | "RECEBIDO"
  | "PROCESSANDO"
  | "AGUARDANDO_REVISAO"
  | "APROVADO"
  | "ENVIADO_BANCO"
  | "CONCILIADO"
  | "REJEITADO"
  | "ERRO";

export type StatusPagamento =
  | "VALIDO"
  | "CORRIGIVEL"
  | "BLOQUEADO"
  | "APROVADO"
  | "REJEITADO"
  | "PAGO"
  | "NAO_PAGO";

export type ModalidadePagamento = "PIX" | "TED" | "TRANSF_UNICRED";

export interface ClienteResumo {
  id: string;
  nome: string;
  cnpj: string | null;
}

export interface Cliente extends ClienteResumo {
  email_contato: string | null;
  ativo: boolean;
}

export interface LoteResumo {
  id: string;
  cliente: ClienteResumo;
  nome_arquivo: string;
  referencia: string | null;
  status: StatusLote;
  total_pagamentos: number;
  total_validos: number;
  total_corrigiveis: number;
  total_bloqueados: number;
  valor_total_centavos: number;
  created_at: string;
  aprovado_at: string | null;
}

export interface Pagamento {
  id: string;
  linha_planilha: number;
  nome: string;
  cpf_mascarado: string;
  cpf_sugerido: string | null;
  cpf_original: string | null;
  banco_codigo: string | null;
  conta_mascarada: string | null;
  valor_centavos: number;
  modalidade: ModalidadePagamento;
  chave_pix: string | null;
  status: StatusPagamento;
  codigos_erro: string | null;
  mensagens_validacao: string | null;
}

export interface LoteDetalhe extends LoteResumo {
  hash_conteudo: string;
  hash_arquivo_cnab: string | null;
  nome_arquivo_cnab: string | null;
  pagamentos: Pagamento[];
}

export interface AprovacaoResponse {
  success: boolean;
  lote_id: string;
  nome_arquivo: string;
  hash_arquivo: string;
  quantidade_pagamentos: number;
  valor_total_centavos: number;
  download_url: string;
}

// =============================================================================
// Dashboard Executivo
// =============================================================================

export type SaudeContrato = "saudavel" | "atencao" | "critico";

export interface ContratoFinanceiro {
  cliente_id: string;
  cliente_nome: string;
  receita_mes_centavos: number;
  custo_mes_centavos: number;
  margem_pct: number;
  margem_delta_pp: number; // pontos percentuais vs mês anterior
  saude: SaudeContrato;
  lotes_mes: number;
  pagamentos_mes: number;
  ultima_atividade: string; // ISO
}

export interface ProjecaoMensal {
  mes: string; // ex.: "Jan/26"
  receita_centavos: number;
  meta_centavos: number;
  realizado: boolean;
}

export interface KPIOperacional {
  lotes_processados: number;
  lotes_aguardando: number;
  tempo_medio_processamento_min: number;
  taxa_erro_pct: number;
  pagamentos_mes: number;
  conciliados_pct: number;
}

export type AlertaSeveridade = "critico" | "atencao" | "info";

export interface Alerta {
  id: string;
  severidade: AlertaSeveridade;
  titulo: string;
  descricao: string;
  cliente_nome: string | null;
  acao_sugerida: string | null;
  created_at: string;
}

export interface RenovacaoProxima {
  cliente_id: string;
  cliente_nome: string;
  vencimento: string; // ISO
  dias_restantes: number;
  margem_atual_pct: number;
  recomendacao: "manter" | "reajustar" | "renegociar_urgente";
  reajuste_sugerido_pct: number | null;
}

// =============================================================================
// Contratos — configuração comercial editável pelo BPO
// =============================================================================

/**
 * Configuração de cobrança. Cada campo é INDEPENDENTE — o BPO pode
 * combinar livremente: % sobre volume + mensalidade, ou só por pagamento, etc.
 * Campos zerados não entram no cálculo.
 */
export interface ConfiguracaoCobranca {
  /** Valor fixo cobrado todo mês (independente de volume). Em centavos. */
  mensalidade_centavos: number;
  /** Cobrança variável por pagamento processado. Em centavos. */
  taxa_por_pagamento_centavos: number;
  /** Percentual cobrado sobre o volume movimentado. Em base points (120 = 1,20%). */
  percentual_volume_bp: number;
  /** Volume médio mensal estimado processado pra esse cliente. Em centavos. */
  volume_medio_mensal_centavos: number;
}

/** Configuração de custo operacional do BPO em cima desse contrato. */
export interface ConfiguracaoCusto {
  /** Custo fixo mensal (mão de obra dedicada, etc). Em centavos. */
  custo_fixo_mensal_centavos: number;
  /** Custo variável como % da receita (banco, infra). */
  custo_variavel_pct: number;
}

export interface ContratoConfig {
  cliente_id: string;
  cliente_nome: string;
  cliente_cnpj: string | null;
  cobranca: ConfiguracaoCobranca;
  custo: ConfiguracaoCusto;
  meta_mensal_centavos: number;
  vencimento: string; // ISO
  ativo: boolean;
}

// =============================================================================
// Admin — gestão de usuários e relatórios estratégicos
// =============================================================================

export interface UserAdmin {
  id: string;
  email: string;
  nome: string;
  role: UserRole;
  ativo: boolean;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
}

export interface CriarUsuarioPayload {
  email: string;
  nome: string;
  role: UserRole;
  senha: string;
}

export interface AtualizarUsuarioPayload {
  nome?: string;
  role?: UserRole;
  ativo?: boolean;
}

export interface ErrosPorOperador {
  operador_id: string | null;
  operador_nome: string;
  operador_email: string | null;
  total_lotes: number;
  total_pagamentos: number;
  total_bloqueados: number;
  total_corrigiveis: number;
  taxa_erro_pct: number;
  valor_bloqueado_centavos: number;
}

export interface ErrosPorTipo {
  codigo: string;
  descricao: string;
  quantidade: number;
  valor_centavos: number;
}

export interface ErrosPorHospital {
  cliente_id: string;
  cliente_nome: string;
  total_lotes: number;
  total_pagamentos: number;
  total_bloqueados: number;
  taxa_erro_pct: number;
}

export interface RelatorioErros {
  periodo_inicio: string;
  periodo_fim: string;
  total_lotes_processados: number;
  total_pagamentos: number;
  total_bloqueados: number;
  total_corrigiveis: number;
  valor_total_centavos: number;
  valor_bloqueado_centavos: number;
  taxa_erro_pct: number;
  por_operador: ErrosPorOperador[];
  por_tipo_erro: ErrosPorTipo[];
  por_hospital: ErrosPorHospital[];
}

export interface DevolucaoBanco {
  pagamento_id: string;
  lote_id: string;
  lote_nome: string;
  cliente_nome: string;
  linha_planilha: number;
  nome_beneficiario: string;
  cpf_mascarado: string;
  valor_centavos: number;
  retorno_codigo: string | null;
  retorno_descricao: string | null;
  motivo_conhecido: boolean;
  pago_at: string | null;
  operador_nome: string | null;
}

export interface DevolucoesPorMotivo {
  codigo: string;
  descricao: string;
  quantidade: number;
  valor_centavos: number;
}

export interface RelatorioDevolucoes {
  periodo_inicio: string;
  periodo_fim: string;
  total_devolucoes: number;
  total_motivo_conhecido: number;
  total_motivo_desconhecido: number;
  valor_total_devolvido_centavos: number;
  por_motivo: DevolucoesPorMotivo[];
  devolucoes: DevolucaoBanco[];
}

// =============================================================================
// Empresa Pagadora — dados que vão no Header do CNAB 240
// =============================================================================

export type TipoInscricao = "CPF" | "CNPJ";

export interface EmpresaPagadora {
  id: string;
  razao_social: string;
  nome_fantasia: string | null;
  tipo_inscricao: TipoInscricao;
  cnpj_cpf: string;

  banco_codigo: string;
  agencia: string;
  agencia_dv: string | null;
  conta_mascarada: string;
  conta_dv: string;
  codigo_convenio: string;

  endereco_logradouro: string;
  endereco_numero: string;
  endereco_complemento: string | null;
  endereco_cidade: string;
  endereco_cep: string;
  endereco_uf: string;

  proximo_numero_sequencial: number;
  ativo: boolean;
  created_at: string;
  updated_at: string;
}

export interface EmpresaPagadoraPayload {
  razao_social: string;
  nome_fantasia?: string | null;
  tipo_inscricao: TipoInscricao;
  cnpj_cpf: string;

  banco_codigo: string;
  agencia: string;
  agencia_dv?: string | null;
  conta: string;
  conta_dv: string;
  codigo_convenio: string;

  endereco_logradouro: string;
  endereco_numero: string;
  endereco_complemento?: string | null;
  endereco_cidade: string;
  endereco_cep: string;
  endereco_uf: string;

  proximo_numero_sequencial: number;
}

// =============================================================================
// Jarvis — WhatsApp + LLM
// =============================================================================

export type DirecaoMensagemWpp = "INBOUND" | "OUTBOUND";
export type StatusInstanciaWpp =
  | "DESCONECTADA"
  | "AGUARDANDO_QR"
  | "CONECTADA"
  | "ERRO";

export interface WhatsAppUserOut {
  id: string;
  user_id: string;
  user_nome: string;
  user_email: string;
  user_role: UserRole;
  numero_e164: string;
  apelido: string | null;
  pode_aprovar_pagamento: boolean;
  ativo: boolean;
  created_at: string;
}

export interface WhatsAppMensagemOut {
  id: string;
  numero_e164: string;
  user_id: string | null;
  direcao: DirecaoMensagemWpp;
  texto: string;
  tools_usadas: Array<{ tool: string; args: Record<string, unknown>; resultado: unknown }> | null;
  tokens_prompt: number;
  tokens_resposta: number;
  duracao_ms: number;
  erro: string | null;
  created_at: string;
}

export interface InstanciaWpp {
  id: string;
  wuzapi_instance_id: string;
  numero_bot: string | null;
  status: StatusInstanciaWpp;
  ativa: boolean;
  created_at: string;
  updated_at: string;
}

export interface QRCodeWpp {
  qr_base64: string | null;
  status: StatusInstanciaWpp;
}

// =============================================================================
// Fichas de Plantão — módulo OCR (substitui planilha do escalista)
// =============================================================================

export type StatusFicha =
  | "RECEBIDA"
  | "PROCESSANDO"
  | "EXTRAIDA"
  | "REVISADA"
  | "CONVERTIDA"
  | "ERRO";

export interface LinhaExtraida {
  cpf: string | null;
  nome: string | null;
  valor_centavos: number | null;
  qtd_plantoes: number | null;
  horas: number | null;
  banco_codigo: string | null;
  agencia: string | null;
  conta: string | null;
  chave_pix: string | null;
  linha_origem: string;
  avisos: string[];
}

export interface FichaResumo {
  id: string;
  cliente: ClienteResumo;
  nome_arquivo: string;
  mime_type: string;
  tamanho_bytes: number;
  status: StatusFicha;
  paginas_ocr: number;
  total_linhas: number;
  valor_total_centavos: number;
  mensagem_erro: string | null;
  lote_gerado_id: string | null;
  created_at: string;
  revisado_at: string | null;
}

export interface FichaDetalhe extends FichaResumo {
  texto_ocr: string | null;
  linhas_extraidas: LinhaExtraida[];
  metadados: Record<string, unknown> | null;
}

export interface KPIHero {
  lucro_liquido_centavos: number;
  receita_total_centavos: number;
  custo_total_centavos: number;
  margem_media_pct: number;
  delta_lucro_pct: number;
  meta_total_centavos: number;
  meta_atingida_pct: number;
}

export interface DashboardExecutivo {
  gerado_em: string;
  mes_referencia: string; // ex.: "Junho/2026"
  kpi_hero: KPIHero;
  contratos: ContratoFinanceiro[];
  projecao_12m: ProjecaoMensal[];
  kpi_operacional: KPIOperacional;
  alertas: Alerta[];
  renovacoes_proximas: RenovacaoProxima[];
  receita_prevista_centavos: number;
  margem_prevista_centavos: number;
}

// =============================================================================
// Painel do Coordenador
// =============================================================================

export interface FichaCoordenadorResumo {
  id: string;
  cliente_nome: string;
  nome_arquivo: string;
  competencia: string | null;
  status: string;
  total_linhas: number;
  valor_total_centavos: number;
  created_at: string;
  duplicada_de_id: string | null;
  motivo_duplicidade: string | null;
}

export interface BancoHorasMedico {
  cpf_mascarado: string;
  nome: string;
  qtd_fichas: number;
  horas_total: number;
  valor_total_centavos: number;
  competencias: string[];
  ultima_ficha_id: string;
  ultima_ficha_em: string;
}

export interface PainelCoordenador {
  gerado_em: string;
  fichas_recentes: FichaCoordenadorResumo[];
  banco_horas: BancoHorasMedico[];
  qtd_fichas_total: number;
  qtd_fichas_mes: number;
  qtd_lotes_gerados: number;
  valor_total_mes_centavos: number;
  duplicatas_potenciais: number;
}

// =============================================================================
// Contratos (backend real, substitui mock do demo.ts)
// =============================================================================

export interface ContratoBackend extends ContratoConfig {
  id: string;
  vigencia_inicio: string; // ISO date
  observacoes: string | null;
}

export interface SalvarContratoPayload {
  cobranca: ConfiguracaoCobranca;
  custo: ConfiguracaoCusto;
  meta_mensal_centavos: number;
  vencimento: string | null;
  observacoes: string | null;
}
