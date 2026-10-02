# 🚛 PGSC Telemetria - Programa de Gestão do Comportamento Seguro do Condutor

<div align="center">

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-2.3+-000000?style=for-the-badge&logo=flask&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-07405E?style=for-the-badge&logo=sqlite&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![ReportLab](https://img.shields.io/badge/PDF_Engine-ReportLab-red?style=for-the-badge)

**Sistema corporativo de gestão de segurança viária, análise de telemetria veicular (Gobrax & Maxtrack Smart Drive), acompanhamento de condutores e cálculo de reincidência.**

[Visão Geral](#-visão-geral) • [Recursos Principais](#-recursos-principais) • [Arquitetura](#-arquitetura-do-projeto) • [Métricas & Efetividade](#-métricas-de-efetividade--reincidência) • [Como Rodar](#-como-rodar-o-projeto) • [Estrutura de Pastas](#-estrutura-do-código)

</div>

---

## 🎯 Visão Geral

O **PGSC Telemetria** é uma plataforma corporativa desenvolvida para a gestão e melhoria contínua da condução de veículos pesados. O sistema processa dados brutos de telemetria veicular, mapeia condutores com comportamento de risco (excesso de velocidade, freadas bruscas, rotação fora da faixa verde, aceleração excessiva e fadiga) e gerencia todo o ciclo de tratativas pedagógicas, reciclagens e acompanhamentos de 15, 30 e 60 dias.

### 🏆 Impacto no Negócio
- **Redução de Acidentes e Sinistros**: Acompanhamento focado nos motoristas com notas críticas.
- **Economia de Combustível e Manutenção**: Condução dentro da faixa verde e diminuição de desgastes severos de freios e pneus.
- **Auditoria e Compliance**: Dossiês completos em PDF gerados automaticamente para auditorias de clientes e certificações de segurança.

---

## ✨ Recursos Principais

### 1. 📋 Central de Ações & Kanban de Tratativas
- Visualização em 5 etapas padronizadas:
  1. **Identificados**: Condutores apontados pelos relatórios de telemetria semanal.
  2. **Notificados**: Alertas emitidos para os instrutores e supervisores locais.
  3. **Em Tratativa**: Acompanhamento em cabine (RideCheck) e reciclagem teórica/prática.
  4. **Concluídos**: Tratativa finalizada e registrada no histórico do motorista.
  5. **Acompanhamento (Pós-Tratativa)**: Checkpoints automáticos aos 15, 30 e 60 dias para validar mudança de comportamento.

### 2. 📊 Cálculo de Efetividade e Taxa de Reincidência
- **Meta Corporativa de Reincidência**: `< 15%`
- **Meta Corporativa de Efetividade**: `> 85%`
- Comparação estatística automatizada da nota do motorista nos 30 dias anteriores à tratativa versus os 30 dias posteriores.

### 3. 📑 Geração Automática de Pastas / Dossiês em PDF
- Módulo nativo com ReportLab para exportação de:
  - Ficha cadastral com foto e histórico completo de infrações.
  - Termos de alinhamento e compromisso pedagógico assinados.
  - Gráficos comparativos de evolução de telemetria.

### 4. 👥 Controle de Acesso e Permissões Granulares (RBAC)
- **Administrador**: Gestão total de usuários, parâmetros globais e configurações de SMTP/sistemas.
- **Coordenação / Gestor**: Visualização executiva de indicadores, rankings e aprovações.
- **Instrutor**: Lançamento de tratativas, acompanhamentos práticos e feedbacks de condutores.
- **Perfil Treinamento**: Acesso restrito exclusivamente às operações vinculadas ao usuário, sem permissão para cadastrar ou alterar parâmetros sensíveis.

---

## 🏗️ Arquitetura do Projeto

```
pgsc-telemetria/
├── app.py                   # Ponto de entrada da aplicação Flask e rotas Web/API
├── auth.py                  # Camada de autenticação, sessões seguras e RBAC
├── database.py              # Esquema de dados, queries parametrizadas e migrações
├── efetividade.py           # Algoritmos estatísticos de cálculo de reincidência
├── generate_pdf_folder.py   # Gerador de relatórios e prontuários em PDF
├── templates/               # Views renderizadas pelo servidor (Jinja2)
│   ├── index.html           # Dashboard executivo e Kanban
│   ├── condutores.html      # Tabela de condutores e filtros avançados
│   ├── reciclagem.html      # Fichas de reciclagem e tratativa
│   └── ...
├── static/                  # CSS responsivo, JavaScript interativo e assets
└── Dockerfile               # Containerização pronta para produção
```

---

## 📈 Métricas de Efetividade & Reincidência

O módulo `efetividade.py` implementa as diretrizes do Procedimento Corporativo de Gestão de Condução Segura:

$$	ext{Taxa de Reincidência} = rac{	ext{Condutores reincidentes no período}}{	ext{Total de condutores submetidos a tratativa}} 	imes 100$$

$$	ext{Efetividade} = 100\% - 	ext{Taxa de Reincidência}$$

Critérios de classificação:
- 🟢 **Excelente**: Efetividade $\ge 90\%$
- 🟡 **Em Atenção**: Efetividade entre $80\%$ e $89\%$
- 🔴 **Crítico**: Efetividade $< 80\%$ (necessidade de intervenção na operação)

---

## 🚀 Como Rodar o Projeto

### Opção 1: Rodando Localmente com Python
```bash
# 1. Clone o repositório
git clone https://github.com/canestrimatheus-ai/pgsc-telemetria.git
cd pgsc-telemetria

# 2. Crie e ative o ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/macOS
# ou: venv\Scriptsctivate  # Windows

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Configure o arquivo de ambiente
cp .env.example .env

# 5. Inicie a aplicação
python app.py
```
Acesse `http://localhost:5000`.

### Opção 2: Rodando via Docker
```bash
# Build da imagem
docker build -t pgsc-telemetria .

# Execução do container
docker run -d -p 5000:5000 --name pgsc-app --env-file .env pgsc-telemetria
```

---

## ⚙️ Variáveis de Ambiente (`.env`)

```env
FLASK_ENV=production
PORT=5000
SECRET_KEY=defina_uma_chave_criptografica_forte

# Envio de Notificações por E-mail (SMTP)
SMTP_HOST=smtp.seuprovedor.com
SMTP_PORT=587
SMTP_USER=seu_usuario@email.com
SMTP_PASS=sua_senha_smtp
SMTP_FROM=nao-responda@suaempresa.com
```

---

<div align="center">
Desenvolvido por <strong>Matheus Canestri</strong> para segurança viária, eficiência operacional e inovação em frotas.
</div>
