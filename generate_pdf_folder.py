import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

# ── Document Setup ──────────────────────────────────────────
pdf_filename = "Folder_Apresentacao_PGCSC.pdf"
doc = SimpleDocTemplate(
    pdf_filename,
    pagesize=A4,
    leftMargin=30,
    rightMargin=30,
    topMargin=35,
    bottomMargin=35
)

# Colors
NAVY = colors.HexColor("#0D1B2A")
BLUE = colors.HexColor("#1A56DB")
LIGHT_BLUE = colors.HexColor("#EBF2FF")
DARK_BLUE = colors.HexColor("#0F172A")
AMBER = colors.HexColor("#D97706")
RED = colors.HexColor("#DC2626")
GREEN = colors.HexColor("#059669")
TEXT_GRAY = colors.HexColor("#475569")
BG_GRAY = colors.HexColor("#F8FAFC")
BORDER_GRAY = colors.HexColor("#E2E8F0")

# Styles
styles = getSampleStyleSheet()

title_style = ParagraphStyle(
    'CoverTitle',
    parent=styles['Heading1'],
    fontName='Helvetica-Bold',
    fontSize=22,
    leading=26,
    textColor=colors.white,
    alignment=0
)

subtitle_style = ParagraphStyle(
    'CoverSubtitle',
    parent=styles['Normal'],
    fontName='Helvetica',
    fontSize=11,
    leading=15,
    textColor=colors.HexColor("#94A3B8"),
    alignment=0
)

h1_style = ParagraphStyle(
    'SectionH1',
    parent=styles['Heading2'],
    fontName='Helvetica-Bold',
    fontSize=14,
    leading=18,
    textColor=NAVY,
    spaceBefore=10,
    spaceAfter=6
)

h2_style = ParagraphStyle(
    'SectionH2',
    parent=styles['Heading3'],
    fontName='Helvetica-Bold',
    fontSize=11,
    leading=15,
    textColor=BLUE,
    spaceBefore=6,
    spaceAfter=4
)

body_style = ParagraphStyle(
    'BodyTextCustom',
    parent=styles['BodyText'],
    fontName='Helvetica',
    fontSize=9.5,
    leading=13.5,
    textColor=DARK_BLUE,
    spaceAfter=6
)

bullet_style = ParagraphStyle(
    'BulletCustom',
    parent=styles['Normal'],
    fontName='Helvetica',
    fontSize=9,
    leading=13,
    textColor=TEXT_GRAY,
    leftIndent=12,
    spaceAfter=3
)

badge_style = ParagraphStyle(
    'BadgeText',
    fontName='Helvetica-Bold',
    fontSize=8.5,
    leading=11,
    textColor=colors.white,
    alignment=1
)

# Numbered Canvas for Page Numbers & Headers
class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        # Top banner on pages > 1
        if self._pageNumber > 1:
            self.setFillColor(NAVY)
            self.rect(0, 815, 595.27, 27, fill=1, stroke=0)
            self.setFillColor(colors.white)
            self.setFont("Helvetica-Bold", 9)
            self.drawString(30, 824, "PGCSC · EXPRESSO NEPOMUCENO — Folder de Apresentação")
            self.drawRightString(565, 824, "Sistema Corporativo de Gestão de Reciclagens")
            
        # Footer on all pages
        self.setStrokeColor(BORDER_GRAY)
        self.setLineWidth(0.5)
        self.line(30, 30, 565.27, 30)
        
        self.setFillColor(TEXT_GRAY)
        self.setFont("Helvetica", 8)
        self.drawString(30, 18, "Expresso Nepomuceno S/A — Todos os direitos reservados.")
        self.drawRightString(565.27, 18, f"Página {self._pageNumber} de {page_count}")
        self.restoreState()


# Image directory
IMG_DIR = r"C:\Users\matheuscamilo\.gemini\antigravity\brain\857f279a-440a-4daa-be23-67da5bcc8317"
img_kanban = os.path.join(IMG_DIR, "pgcsc_kanban_view_1785340366804.jpg")
img_painel = os.path.join(IMG_DIR, "pgcsc_painel_view_1785340384912.jpg")
img_prontuario = os.path.join(IMG_DIR, "pgcsc_prontuario_view_1785340404681.jpg")
img_importar = os.path.join(IMG_DIR, "pgcsc_importar_view_1785340420833.jpg")

story = []

# ════════════════════════════════════════════════════════════
# CAPA & VISÃO GERAL (Page 1)
# ════════════════════════════════════════════════════════════

# Header Box Table
header_content = [
    [Paragraph("<b>PGCSC — SISTEMA DE GESTÃO DE RECICLAGENS</b>", title_style)],
    [Paragraph("Programa Corporativo de Prevenção ao Excesso de Velocidade | Expresso Nepomuceno", subtitle_style)]
]
header_table = Table(header_content, colWidths=[535])
header_table.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,-1), NAVY),
    ('TOPPADDING', (0,0), (-1,-1), 16),
    ('BOTTOMPADDING', (0,0), (-1,-1), 16),
    ('LEFTPADDING', (0,0), (-1,-1), 16),
    ('RIGHTPADDING', (0,0), (-1,-1), 16),
    ('CORNERPAD', (0,0), (-1,-1), 0),
]))
story.append(header_table)
story.append(Spacer(1, 14))

# Intro Box
story.append(Paragraph("<b>Apresentação do Sistema Corporativo</b>", h1_style))
intro_p = Paragraph(
    "O <b>PGCSC</b> é a plataforma corporativa desenvolvida para gerenciar, monitorar e tratar "
    "motoristas reincidentes em excesso de velocidade na <b>Expresso Nepomuceno</b>. O sistema "
    "integra em um único ambiente digital a <b>Telemetria, DECAM, RH, Gestores de Operação e Instrutores</b>, "
    "garantindo que 100% dos enquadramentos sigam o procedimento oficial corporativo sem dependência de controles manuais.",
    body_style
)
story.append(intro_p)
story.append(Spacer(1, 10))

# 4 Key Value Pillars Table
story.append(Paragraph("<b>Principais Pilares da Plataforma</b>", h2_style))

p1 = Paragraph("<b>⚡ Automação Total</b><br/><font color='#475569'>Leitura direta de planilhas mensal da telemetria (.xlsx) com recálculo automático de faixas de risco.</font>", body_style)
p2 = Paragraph("<b>📊 Visão Executiva</b><br/><font color='#475569'>Dashboards em tempo real com indicadores globais de efetividade, taxa de reincidência e relatórios.</font>", body_style)
p3 = Paragraph("<b>🎯 Prontuário 360°</b><br/><font color='#475569'>Histórico individual por condutor, linha do tempo de tratamento, atribuição de instrutores e PDIs.</font>", body_style)
p4 = Paragraph("<b>🛡️ Gestão de Riscos</b><br/><font color='#475569'>Classificação automática em faixas Amarela, Laranja e Vermelha com alertas preventivos de gravidade.</font>", body_style)

pillars_data = [
    [p1, p2],
    [p3, p4]
]
pillars_table = Table(pillars_data, colWidths=[262, 262])
pillars_table.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,-1), BG_GRAY),
    ('BOX', (0,0), (-1,-1), 1, BORDER_GRAY),
    ('INNERGRID', (0,0), (-1,-1), 1, BORDER_GRAY),
    ('TOPPADDING', (0,0), (-1,-1), 10),
    ('BOTTOMPADDING', (0,0), (-1,-1), 10),
    ('LEFTPADDING', (0,0), (-1,-1), 12),
    ('RIGHTPADDING', (0,0), (-1,-1), 12),
]))
story.append(pillars_table)
story.append(Spacer(1, 14))

# Matrix Table Explanation
story.append(Paragraph("<b>Matriz Corporativa de Tratamento por Nível de Risco</b>", h2_style))
matriz_data = [
    [Paragraph("<b>Faixa</b>", body_style), Paragraph("<b>Nível</b>", body_style), Paragraph("<b>Critério de Enquadramento</b>", body_style), Paragraph("<b>Ação Requerida / Tratamento</b>", body_style)],
    [Paragraph("<font color='#D97706'><b>🟡 AMARELA</b></font>", body_style), Paragraph("Nível 1", body_style), Paragraph("1º evento em 12 meses", body_style), Paragraph("Reciclagem Preventiva com Instrutor DECAM", body_style)],
    [Paragraph("<font color='#EA580C'><b>🟠 LARANJA</b></font>", body_style), Paragraph("Nível 2 e 3", body_style), Paragraph("2 a 3 eventos em 12 meses", body_style), Paragraph("PDI + Viagem Assistida com Instrutor", body_style)],
    [Paragraph("<font color='#DC2626'><b>🔴 VERMELHA</b></font>", body_style), Paragraph("Nível 4", body_style), Paragraph("4+ eventos (Reincidência Crítica)", body_style), Paragraph("Comitê de Avaliação Executiva + Suspensão", body_style)],
]
matriz_table = Table(matriz_data, colWidths=[85, 55, 170, 215])
matriz_table.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,0), LIGHT_BLUE),
    ('TEXTCOLOR', (0,0), (-1,0), NAVY),
    ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ('TOPPADDING', (0,0), (-1,-1), 6),
    ('GRID', (0,0), (-1,-1), 0.5, BORDER_GRAY),
]))
story.append(matriz_table)

story.append(PageBreak())

# ════════════════════════════════════════════════════════════
# PAGE 2: MÓDULO 1 — CENTRAL DE AÇÕES (KANBAN)
# ════════════════════════════════════════════════════════════
story.append(Paragraph("1. Central de Ações — Quadro Kanban de Tratamento", h1_style))
story.append(Paragraph(
    "A <b>Central de Ações</b> é a tela principal de operação. Ela organiza visualmente todos os motoristas "
    "monitorados em <b>5 colunas estruturadas</b> conforme o estágio do procedimento corporativo:",
    body_style
))

if os.path.exists(img_kanban):
    story.append(Image(img_kanban, width=525, height=270))
    story.append(Spacer(1, 8))

story.append(Paragraph("<b>Funcionalidades e Recursos da Tela:</b>", h2_style))
story.append(Paragraph("• <b>Busca Instantânea por Nome ou Matrícula:</b> Campo de pesquisa inteligente com marcação amarela (highlight) no texto para localização imediata.", bullet_style))
story.append(Paragraph("• <b>Filtros por Operação e Gestor:</b> Seletores suspensos para isolar filiais específicas (ex: BRACELL, SUZANO) ou gestores de frota.", bullet_style))
story.append(Paragraph("• <b>Expansão Dinâmica por Coluna:</b> Botão <i>'▼ Ver todos os X motoristas'</i> para carregar 100% da lista sem sair da tela.", bullet_style))
story.append(Paragraph("• <b>Cards Compactos Informativos:</b> Exibe código da matrícula, faixa de risco, nome em formato legível (Title Case), filial e contagem de reciclagens.", bullet_style))
story.append(Paragraph("• <b>Contadores em Tempo Real:</b> Header com resumo das reciclagens em aberto, vencidas e agendadas.", bullet_style))

story.append(PageBreak())

# ════════════════════════════════════════════════════════════
# PAGE 3: MÓDULO 2 — PAINEL EXECUTIVO & ANALÍTICOS
# ════════════════════════════════════════════════════════════
story.append(Paragraph("2. Painel Executivo — KPIs & Dashboards Estratégicos", h1_style))
story.append(Paragraph(
    "O <b>Painel Executivo</b> foi desenhado para a diretoria e gerências de operação, consolidando os principais "
    "indicadores de desempenho e métricas de efetividade do programa em tempo real:",
    body_style
))

if os.path.exists(img_painel):
    story.append(Image(img_painel, width=525, height=270))
    story.append(Spacer(1, 8))

story.append(Paragraph("<b>Métricas e Gráficos Disponíveis:</b>", h2_style))
story.append(Paragraph("• <b>KPIs Principais:</b> Total de Motoristas Ativos, Acumulado de Reciclagens, Volume de Reincidentes, Taxa de Reincidência (%) e Efetividade Global (%).", bullet_style))
story.append(Paragraph("• <b>📈 Gráfico de Evolução Mensal:</b> Comparativo de reciclagens aplicadas vs. casos de reincidência mês a mês.", bullet_style))
story.append(Paragraph("• <b>🎯 Gráfico de Faixas de Risco:</b> Distribuição percentual da frota entre as faixas Amarela, Laranja e Vermelha.", bullet_style))
story.append(Paragraph("• <b>🏢 Ranking de Operações:</b> Comparativo de volume de ocorrências entre filiais e unidades de negócio.", bullet_style))

story.append(PageBreak())

# ════════════════════════════════════════════════════════════
# PAGE 4: MÓDULO 3 — PRONTUÁRIO INDIVIDUAL DO MOTORISTA
# ════════════════════════════════════════════════════════════
story.append(Paragraph("3. Prontuário do Condutor — Ficha 360° do Motorista", h1_style))
story.append(Paragraph(
    "Ao clicar em qualquer card do Kanban ou botão de visualização, a plataforma abre a <b>Ficha 360° do Motorista</b>. "
    "Esta tela centraliza todo o histórico do condutor, permitindo gerenciar o ciclo de vida completo do tratamento:",
    body_style
))

if os.path.exists(img_prontuario):
    story.append(Image(img_prontuario, width=525, height=270))
    story.append(Spacer(1, 8))

story.append(Paragraph("<b>Recursos do Prontuário:</b>", h2_style))
story.append(Paragraph("• <b>Linha do Tempo de Progresso (Stepper):</b> Acompanhamento visual dos 4 estágios (Enquadramento ➔ Reciclagem ➔ PDI / Reunião ➔ Monitoramento 90d).", bullet_style))
story.append(Paragraph("• <b>Histórico de Ocorrências nos últimos 12 meses:</b> Lista de reciclagens com data de envio, instrutor DECAM responsável e status atual.", bullet_style))
story.append(Paragraph("• <b>Atualização Rápida de Status:</b> Modal integrado para alterar o status da reciclagem (<i>Agendado, Concluído, Cancelado, Mensagem Enviada</i>) e registrar observações.", bullet_style))

story.append(PageBreak())

# ════════════════════════════════════════════════════════════
# PAGE 5: MÓDULO 4 — IMPORTAÇÃO AUTOMÁTICA & EXPORTAÇÃO
# ════════════════════════════════════════════════════════════
story.append(Paragraph("4. Importação Automática da Telemetria & Exportação", h1_style))
story.append(Paragraph(
    "Para eliminar o trabalho manual de digitação, a plataforma conta com um módulo de <b>importação inteligente "
    "de planilhas Excel (.xlsx)</b> enviado mensalmente pela equipe de Telemetria:",
    body_style
))

if os.path.exists(img_importar):
    story.append(Image(img_importar, width=525, height=250))
    story.append(Spacer(1, 8))

story.append(Paragraph("<b>Como Funciona a Importação:</b>", h2_style))
story.append(Paragraph("1. <b>Arrastar e Soltar (Drag & Drop):</b> O usuário arrasta o arquivo Excel da remessa mensal diretamente para a caixa de importação.", bullet_style))
story.append(Paragraph("2. <b>Processamento Automático:</b> O sistema lê todos os registros, identifica motoristas novos e reincidentes, calcula o volume acumulado de 12 meses e ajusta as faixas de risco instantaneamente.", bullet_style))
story.append(Paragraph("3. <b>Exportação Completa para Excel:</b> Botão <i>'📤 Exportar Dados'</i> que gera uma planilha consolidada com 3 abas (Base de Motoristas, Histórico de Reciclagens e Registros de PDIs).", bullet_style))

story.append(Spacer(1, 14))

# Conclusion Footer Box
concl_content = [
    [Paragraph("<b>💡 RESUMO DOS BENEFÍCIOS CORPORATIVOS</b>", ParagraphStyle('WTitle', fontName='Helvetica-Bold', fontSize=11, textColor=colors.white))],
    [Paragraph("<b>✓ Zero Erro Humano:</b> Processamento 100% automatizado das planilhas mensais da telemetria.<br/>"
               "<b>✓ Transparência Total:</b> Histórico auditável por condutor, gestor e filial.<br/>"
               "<b>✓ Agilidade Operacional:</b> Interface ultra rápida e expansível em qualquer computador da rede.<br/>"
               "<b>✓ Foco na Prevenção:</b> Identificação precoce dos condutores de maior risco para intervenção do DECAM.",
               ParagraphStyle('WBody', fontName='Helvetica', fontSize=9, leading=13, textColor=colors.white))]
]
concl_table = Table(concl_content, colWidths=[535])
concl_table.setStyle(TableStyle([
    ('BACKGROUND', (0,0), (-1,-1), BLUE),
    ('TOPPADDING', (0,0), (-1,-1), 12),
    ('BOTTOMPADDING', (0,0), (-1,-1), 12),
    ('LEFTPADDING', (0,0), (-1,-1), 14),
    ('RIGHTPADDING', (0,0), (-1,-1), 14),
]))
story.append(concl_table)

# Build Document
doc.build(story, canvasmaker=NumberedCanvas)
print("PDF Folder generated successfully:", pdf_filename)
