// ============================================================
// PGCSC · Dashboard JS v3 — Reformulado conforme reunião
// ============================================================

let _chartMensal = null, _chartFaixas = null, _chartOps = null;
let _chartEfetMensal = null, _chartEfetReinc = null;
let _currentDriverData = null;

// ── Boot ──────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initNav();
    initUpload();
    initFiltersListeners();
    initFormEditar();
    initOverlayClose();
    loadHeaderKPIs();
    loadFilterOptions();

    // Restaurar a última aba ativa salva no localStorage ou no hash da URL
    const savedTab = window.location.hash.replace('#', '') || localStorage.getItem('pgcsc_active_tab') || 'kanban';
    switchTab(savedTab);
});

// ── Navigation ────────────────────────────────────────────
const TAB_TITLES = {
    kanban:        ['Central de Ações', 'Programa corporativo de prevenção ao excesso de velocidade'],
    painel:        ['Painel Executivo', 'Visão consolidada dos indicadores do PGCSC'],
    efetividade:   ['Efetividade das Reciclagens', 'Evento → Indicação → Realização → Acompanhamento → Reincidência'],
    motoristas:    ['Motoristas & Reincidência', 'Base de motoristas monitorados e seus enquadramentos'],
    mensal:        ['Análise Mensal', 'Comparativo histórico mês a mês'],
    operacoes:     ['Operações & Gestores', 'Indicadores por operação e responsável'],
    importar:      ['Importar Planilha', 'Processar remessa mensal da telemetria'],
    configuracoes: ['Configurações', 'Gestão de dados e parâmetros do sistema'],
    usuarios:      ['Gestão de Usuários & Acessos', 'Controle de acessos e permissões por unidade operacional']
};

function switchTab(tab) {
    const role = (window.CURRENT_USER && window.CURRENT_USER.role) || '';
    if (role === 'OPERACAO') {
        if (tab === 'importar' || tab === 'configuracoes' || tab === 'usuarios') {
            tab = 'kanban';
        }
    } else if (role === 'TREINAMENTO') {
        if (tab === 'usuarios' || tab === 'configuracoes') {
            tab = 'kanban';
        }
    }
    if (!TAB_TITLES[tab]) tab = 'kanban';

    // Salvar no localStorage e atualizar hash na URL
    localStorage.setItem('pgcsc_active_tab', tab);
    if (window.location.hash !== '#' + tab) {
        window.history.replaceState(null, null, '#' + tab);
    }

    const btns = document.querySelectorAll('.nav-btn');
    btns.forEach(b => {
        if (b.dataset.tab === tab) b.classList.add('active');
        else b.classList.remove('active');
    });

    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    const section = document.getElementById('tab-' + tab);
    if (section) section.classList.add('active');

    const [h, s] = TAB_TITLES[tab] || ['', ''];
    const pt = document.getElementById('page-title');
    const ps = document.getElementById('page-sub');
    if (pt) pt.textContent = h;
    if (ps) ps.textContent = s;

    // Carregar dados da aba correspondente
    if (tab === 'kanban')     { loadKanban(); }
    if (tab === 'painel')     { populatePainelAnos(); loadPainel(); }
    if (tab === 'efetividade'){ initEfetividadeFilters(); loadEfetividade(); }
    if (tab === 'motoristas') { loadMotoristas(); }
    if (tab === 'mensal')     { loadMensal(); }
    if (tab === 'operacoes')  { loadOperacoes(); }
    if (tab === 'configuracoes') { carregarRegras(); }
    if (tab === 'usuarios')      { loadUsuarios(); }

    // Fechar menu mobile se estiver aberto
    closeMobileSidebar();
}

function toggleMobileSidebar() {
    const sb = document.getElementById('sidebar-nav');
    const bd = document.getElementById('sidebar-backdrop');
    if (!sb) return;
    const isOpen = sb.classList.contains('mobile-open');
    if (isOpen) {
        closeMobileSidebar();
    } else {
        sb.classList.add('mobile-open');
        if (bd) bd.classList.add('open');
        document.body.style.overflow = 'hidden';
    }
}

function closeMobileSidebar() {
    const sb = document.getElementById('sidebar-nav');
    const bd = document.getElementById('sidebar-backdrop');
    if (sb) sb.classList.remove('mobile-open');
    if (bd) bd.classList.remove('open');
    document.body.style.overflow = '';
}

function initNav() {
    const btns = document.querySelectorAll('.nav-btn');
    btns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tab = btn.dataset.tab;
            if (tab) switchTab(tab);
        });
    });
}

// ── Header KPIs (always visible) ─────────────────────────
async function loadHeaderKPIs() {
    try {
        const r = await fetch('/api/kpis');
        const d = await r.json();
        setText('hdr-v-total', d.total_motoristas);
        setText('hdr-v-criticos', d.total_criticos);
        setText('hdr-v-efetividade', d.efetividade_global + '%');
    } catch(e) { console.warn('Header KPIs:', e); }
}

// ── Kanban ────────────────────────────────────────────────
let _kTimer = null;
const _colData = {};  // cache de listas por coluna para expansão

async function loadKanban() {
    const op     = val('k-op');
    const gestor = val('k-gestor');
    const search = val('k-busca');
    const mes    = val('k-mes');
    const ano    = val('k-ano');
    try {
        const r = await fetch(`/api/kanban?operacao=${enc(op)}&gestor=${enc(gestor)}&search=${enc(search)}&mes=${enc(mes)}&ano=${enc(ano)}`);
        const d = await r.json();

        const limit = search ? 50 : 12;

        renderKCol('k-enquadramento', 'cnt-enquadramento', d.enquadramento_1 || [], search, limit);
        renderKCol('k-reinc1',        'cnt-reinc1',        d.reincidencia_1  || [], search, limit);
        renderKCol('k-reinc2',        'cnt-reinc2',        d.reincidencia_2  || [], search, limit);
        renderKCol('k-reinc3',        'cnt-reinc3',        d.reincidencia_3  || [], search, limit);
        renderKCol('k-reinc4',        'cnt-reinc4',        d.reincidencia_4  || [], search, limit);

        const total = (d.enquadramento_1||[]).length
                    + (d.reincidencia_1||[]).length
                    + (d.reincidencia_2||[]).length
                    + (d.reincidencia_3||[]).length
                    + (d.reincidencia_4||[]).length;

        const totalReinc = (d.reincidencia_1||[]).length
                         + (d.reincidencia_2||[]).length
                         + (d.reincidencia_3||[]).length
                         + (d.reincidencia_4||[]).length;

        const totalCriticos = (d.reincidencia_3||[]).length
                            + (d.reincidencia_4||[]).length;

        setText('k-total',        total);
        setText('k-reincidentes', totalReinc);
        setText('k-criticos',     totalCriticos);
    } catch(e) { console.error('Kanban:', e); }
}

function renderKCol(bodyId, cntId, list, search, limit = 12) {
    const body = document.getElementById(bodyId);
    const cnt  = document.getElementById(cntId);
    if (cnt) cnt.textContent = list.length;
    const mCnt = document.getElementById('m-' + cntId);
    if (mCnt) mCnt.textContent = list.length;
    if (!body) return;

    _colData[bodyId] = { list, search };

    if (!list.length) {
        body.innerHTML = `<div class="k-empty">${search ? 'Nenhum resultado para "' + search + '"' : 'Nenhum motorista neste estágio'}</div>`;
        return;
    }

    body.innerHTML = buildCards(list.slice(0, limit), search);

    if (list.length > limit) {
        const btn = document.createElement('button');
        btn.className = 'btn-expand-col';
        btn.textContent = `▼ Ver todos os ${list.length} motoristas desta coluna`;
        btn.onclick = () => expandCol(bodyId);
        body.appendChild(btn);
    }
}

function setMobileKanbanCol(colIndex, btnEl) {
    document.querySelectorAll('.m-ktab').forEach(b => b.classList.remove('active'));
    if (btnEl) btnEl.classList.add('active');

    const cols = document.querySelectorAll('.kanban-body .k-col');
    cols.forEach((col, idx) => {
        if (idx === colIndex) {
            col.classList.add('m-col-active');
            col.style.display = 'flex';
        } else {
            col.classList.remove('m-col-active');
            col.style.display = 'none';
        }
    });
}

function expandCol(bodyId) {
    const body = document.getElementById(bodyId);
    const { list, search } = _colData[bodyId] || {};
    if (!body || !list) return;
    body.innerHTML = buildCards(list, search);
    const btn = document.createElement('button');
    btn.className = 'btn-expand-col secondary';
    btn.textContent = '▲ Recolher';
    btn.onclick = () => renderKCol(bodyId, null, list, search, 12);
    body.appendChild(btn);
}

function buildCards(list, search) {
    return list.map(c => {
        const nomeFormatado = toTitleCase(c.nome);
        const gestorPrimeiro = toTitleCase((c.gestor||'').split(' ')[0]);
        const nomeDisplay = highlightMatch(nomeFormatado, search);
        const consequencia = c.consequencia || 'Reciclagem';
        const situacao = c.situacao || '1º Enquadramento';
        return `
        <div class="k-card" onclick="openProntuario('${c.codigo}')">
            <div class="k-card-top">
                <span class="code-badge">${c.codigo}</span>
                <span class="rp ${c.faixa_risco}">${faixaLabel(c.faixa_risco)}</span>
            </div>
            <div class="k-name">${nomeDisplay}</div>
            <div class="k-op">${c.operacao}</div>
            <div style="margin: 6px 0; padding: 4px 6px; background: rgba(0,0,0,0.04); border-left: 3px solid #3B82F6; border-radius: 3px; font-size: 11px; font-weight: 700; color: var(--c-text);">
                ⚡ ${consequencia}
            </div>
            <div class="k-foot">
                <span>👤 ${gestorPrimeiro}</span>
                <span><strong>${c.total_reciclagens}× no ano</strong></span>
            </div>
        </div>`;
    }).join('');
}

function toTitleCase(str) {
    if (!str) return '';
    const MINUSCULAS = new Set(['da','de','do','das','dos','e','a','o','em','com']);
    return str.toLowerCase().split(' ').map((w, i) =>
        (i === 0 || !MINUSCULAS.has(w)) ? w.charAt(0).toUpperCase() + w.slice(1) : w
    ).join(' ');
}

function highlightMatch(text, search) {
    if (!search || !search.trim()) return text;
    const escaped = search.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(${escaped})`, 'gi');
    return text.replace(regex, '<mark style="background:#FDE047;color:#0F172A;padding:0 1px;border-radius:2px;">$1</mark>');
}

function faixaLabel(f) {
    return { VERMELHA: '🔴 Crítico', LARANJA: '🟠 Reincidente', AMARELA: '🟡 Atenção', VERDE: '🟢 Aderente' }[f] || f;
}

function resetKanbanFilters() {
    setVal('k-busca', '');
    setVal('k-ano', '');
    setVal('k-mes', '');
    setVal('k-op', '');
    setVal('k-gestor', '');
    loadKanban();
}

// ── Filter Options ────────────────────────────────────────
async function loadFilterOptions() {
    try {
        const r = await fetch('/api/filters-options');
        const d = await r.json();

        const isRestrictedRole = (d.user_role === 'OPERACAO' || d.user_role === 'TREINAMENTO');
        const userOps = d.operacoes || [];

        ['k-op', 'm-op'].forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            if (isRestrictedRole && userOps.length === 1) {
                el.innerHTML = `<option value="${userOps[0]}">${userOps[0]}</option>`;
                el.value = userOps[0];
                el.disabled = true;
                el.style.opacity = '0.75';
                el.style.cursor = 'not-allowed';
            } else if (isRestrictedRole && userOps.length > 1) {
                el.disabled = false;
                el.style.opacity = '1';
                el.style.cursor = 'default';
                el.innerHTML = `<option value="">Todas as Minhas Operações (${userOps.length})</option>` +
                    userOps.map(o => `<option value="${o}">${o}</option>`).join('');
            } else {
                el.disabled = false;
                el.style.opacity = '1';
                el.style.cursor = 'default';
                el.innerHTML = `<option value="">Todas as Operações</option>` +
                    userOps.map(o => `<option value="${o}">${o}</option>`).join('');
            }
        });

        // Inicializar Multi-Select do Painel Executivo
        initMultiSelect(d.operacoes || [], d.meses || []);

        const kg = document.getElementById('k-gestor');
        if (kg) {
            kg.innerHTML = `<option value="">Todos os Gestores</option>`;
            d.gestores.forEach(g => kg.innerHTML += `<option value="${g}">${g}</option>`);
        }

        const km = document.getElementById('k-mes');
        if (km) {
            const monthNames = {1:'Janeiro', 2:'Fevereiro', 3:'Março', 4:'Abril', 5:'Maio', 6:'Junho', 7:'Julho', 8:'Agosto', 9:'Setembro', 10:'Outubro', 11:'Novembro', 12:'Dezembro'};
            km.innerHTML = `<option value="">Todos os Meses</option>`;
            (d.meses || []).forEach(m => {
                km.innerHTML += `<option value="${m}">${monthNames[m] || 'Mês ' + m}</option>`;
            });
        }

        // Anos
        ['k-ano', 'p-ano', 'cfg-ano'].forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            el.innerHTML = id === 'cfg-ano'
                ? `<option value="">Selecione o Ano</option>`
                : `<option value="">Todos os Anos</option>`;
            (d.anos || []).forEach(a => {
                el.innerHTML += `<option value="${a}">${a}</option>`;
            });
        });
    } catch(e) { console.warn('Filter options:', e); }
}

// ── Multi-Select State & Logic (Painel BI) ──────────────────
const MONTH_NAMES = {1:'Janeiro',2:'Fevereiro',3:'Março',4:'Abril',5:'Maio',6:'Junho',7:'Julho',8:'Agosto',9:'Setembro',10:'Outubro',11:'Novembro',12:'Dezembro'};
let _msInitialized = false;

function initMultiSelect(opsList = [], mesesList = []) {
    // 1. Popular Opções de Operações
    const opOpts = document.getElementById('ms-op-options');
    if (opOpts) {
        opOpts.innerHTML = opsList.map((op, idx) => `
            <div class="ms-item">
                <input type="checkbox" id="chk-op-${idx}" value="${op}" onchange="onMSChange('ms-op')">
                <label for="chk-op-${idx}" title="${op}">${op}</label>
            </div>
        `).join('');
    }

    // 2. Popular Opções de Meses existentes no banco
    const mesOpts = document.getElementById('ms-mes-options');
    if (mesOpts) {
        mesOpts.innerHTML = (mesesList || []).map(num => `
            <div class="ms-item">
                <input type="checkbox" id="chk-mes-${num}" value="${num}" onchange="onMSChange('ms-mes')">
                <label for="chk-mes-${num}">${MONTH_NAMES[num] || 'Mês ' + num}</label>
            </div>
        `).join('');
    }

    // 3. Listener Global para Fechar Dropdowns ao Clicar Fora
    if (!_msInitialized) {
        document.addEventListener('click', (e) => {
            ['ms-op', 'ms-mes'].forEach(id => {
                const el = document.getElementById(id);
                if (el && !el.contains(e.target)) {
                    el.classList.remove('open');
                }
            });
        });
        _msInitialized = true;
    }
}

function toggleMS(id) {
    const el = document.getElementById(id);
    if (!el) return;
    const wasOpen = el.classList.contains('open');
    document.querySelectorAll('.ms-wrapper').forEach(w => w.classList.remove('open'));
    if (!wasOpen) {
        el.classList.add('open');
        const s = el.querySelector('.ms-search');
        if (s) { s.value = ''; filterMSOptions(id, ''); s.focus(); }
    }
}

function filterMSOptions(id, query) {
    const container = document.getElementById(id + '-options');
    if (!container) return;
    const q = (query || '').toLowerCase().trim();
    container.querySelectorAll('.ms-item').forEach(item => {
        const text = item.textContent.toLowerCase();
        item.style.display = text.includes(q) ? 'flex' : 'none';
    });
}

function toggleMSAll(id) {
    const el = document.getElementById(id);
    if (!el) return;
    const allChk = document.getElementById(id + '-all');
    const checked = allChk ? allChk.checked : false;
    el.querySelectorAll('.ms-options input[type="checkbox"]').forEach(c => {
        const parent = c.closest('.ms-item');
        if (!parent || parent.style.display !== 'none') {
            c.checked = checked;
        }
    });
    updateMSLabel(id);
    loadPainel();
}

function onMSChange(id) {
    updateMSLabel(id);
    loadPainel();
}

function updateMSLabel(id) {
    const el = document.getElementById(id);
    if (!el) return;
    const checkboxes = Array.from(el.querySelectorAll('.ms-options input[type="checkbox"]'));
    const checked = checkboxes.filter(c => c.checked);
    const label = document.getElementById(id + '-label');
    const allChk = document.getElementById(id + '-all');

    if (allChk) {
        allChk.checked = (checked.length === checkboxes.length && checkboxes.length > 0);
    }

    if (id === 'ms-op') {
        if (checked.length === 0 || checked.length === checkboxes.length) {
            if (label) label.textContent = 'Todas as Operações';
        } else if (checked.length === 1) {
            if (label) label.textContent = checked[0].value;
        } else if (checked.length <= 2) {
            if (label) label.textContent = checked.map(c => c.value).join(', ');
        } else {
            if (label) label.textContent = `${checked.length} operações selecionadas`;
        }
    } else if (id === 'ms-mes') {
        if (checked.length === 0 || checked.length === checkboxes.length) {
            if (label) label.textContent = 'Todos os Meses';
        } else if (checked.length === 1) {
            if (label) label.textContent = MONTH_NAMES[checked[0].value] || `Mês ${checked[0].value}`;
        } else if (checked.length <= 2) {
            if (label) label.textContent = checked.map(c => MONTH_NAMES[c.value] || c.value).join(', ');
        } else {
            if (label) label.textContent = `${checked.length} meses selecionados`;
        }
    }
}

function getMSSelected(id) {
    const el = document.getElementById(id);
    if (!el) return [];
    const checkboxes = Array.from(el.querySelectorAll('.ms-options input[type="checkbox"]'));
    const checked = checkboxes.filter(c => c.checked);
    if (checked.length === 0 || checked.length === checkboxes.length) {
        return [];
    }
    return checked.map(c => c.value);
}

function setMSSelected(id, values = []) {
    const el = document.getElementById(id);
    if (!el) return;
    const vSet = new Set(values);
    el.querySelectorAll('.ms-options input[type="checkbox"]').forEach(c => {
        c.checked = vSet.has(c.value);
    });
    updateMSLabel(id);
}

async function populatePainelAnos() {
    try {
        const anos = await fetch('/api/anos-disponiveis').then(r => r.json());
        const sel = document.getElementById('p-ano');
        if (!sel) return;
        const current = sel.value;
        sel.innerHTML = '<option value="">Todos os Anos</option>';
        (anos || []).forEach(a => {
            const opt = document.createElement('option');
            opt.value = a; opt.textContent = a;
            if (String(a) === current) opt.selected = true;
            sel.appendChild(opt);
        });
    } catch(e) {}
}

async function loadPainel() {
    const ops = getMSSelected('ms-op');
    const meses = getMSSelected('ms-mes');
    const ano = val('p-ano') || val('k-ano');

    const opParam = ops.join(',');
    const mesParam = meses.join(',');

    // --- Status Tag
    const tag = document.getElementById('p-op-tag');
    if (tag) {
        let parts = [];
        if (ops.length === 1) parts.push(ops[0]);
        else if (ops.length > 1) parts.push(`${ops.length} filiais`);

        if (meses.length === 1) parts.push(MONTH_NAMES[meses[0]] || `Mês ${meses[0]}`);
        else if (meses.length > 1) parts.push(`${meses.length} meses`);

        if (ano) parts.push(ano);

        tag.innerHTML = parts.length
            ? `<span class="status-pulse"></span> ${parts.join(' · ')}`
            : '<span class="status-pulse"></span> Visão Consolidada';
    }

    const boxTopOp = document.getElementById('box-kpi-top-op');
    if (boxTopOp) {
        boxTopOp.style.display = (ops.length === 1) ? 'none' : 'flex';
    }

    const boxChartOps = document.getElementById('box-card-chart-ops');
    if (boxChartOps) {
        boxChartOps.style.display = (ops.length === 1) ? 'none' : 'block';
    }

    const hdrTop = document.getElementById('hdr-top-motoristas');
    if (hdrTop) {
        if (ops.length === 1) hdrTop.textContent = `🏆 Top Motoristas com Maior Nº de Excessos — Filial ${ops[0]}`;
        else if (ops.length > 1) hdrTop.textContent = `🏆 Top Motoristas com Maior Nº de Excessos (${ops.length} filiais)`;
        else hdrTop.textContent = '🏆 Top 10 Motoristas com Maior Nº de Excessos';
    }

    try {
        const q = `operacao=${enc(opParam)}&ano=${enc(ano)}&mes=${enc(mesParam)}`;
        const [kpi, faixas, mensal, opsRank, topDrivers] = await Promise.all([
            fetch(`/api/kpis?${q}`).then(r => r.json()),
            fetch(`/api/faixas-risco?${q}`).then(r => r.json()),
            fetch(`/api/comparativo-mensal?${q}`).then(r => r.json()),
            fetch(`/api/ranking-operacoes?ano=${enc(ano)}&mes=${enc(mesParam)}`).then(r => r.json()),
            fetch(`/api/top-motoristas-excessos?${q}&limit=10`).then(r => r.json())
        ]);

        setText('kpi-total',     kpi.total_motoristas);
        setText('kpi-rec',       kpi.total_reciclagens);
        setText('kpi-top-op',    kpi.maior_operacao_nome || '–');
        setText('kpi-top-op-sub', ops.length === 1 ? `${kpi.total_reciclagens} excessos nesta filial` : `${kpi.maior_operacao_total || 0} excessos acumulados`);
        setText('kpi-media-rec', kpi.media_reciclagens || '0');
        setText('kpi-reinc',     kpi.total_reincidentes);
        setText('kpi-crit',      kpi.total_criticos);
        setText('kpi-aprovados', kpi.total_aprovados || 0);
        setText('kpi-taxa',      kpi.taxa_reincidencia + '%');
        setText('kpi-efet',      kpi.efetividade_global + '%');

        // Renderizar Tabela BI Top Motoristas por Excessos
        const tbTop = document.getElementById('tbody-top-motoristas-excessos');
        if (tbTop && Array.isArray(topDrivers)) {
            tbTop.innerHTML = topDrivers.map((m, idx) => `
                <tr style="cursor:pointer;" onclick="openProntuario('${m.codigo}')" title="Clique para ver prontuário de ${toTitleCase(m.nome)}">
                    <td><strong>#${idx + 1}</strong></td>
                    <td>
                        <div style="font-weight:600; color:var(--c-text);">${toTitleCase(m.nome)}</div>
                        <div style="font-size:11px; color:var(--c-muted);">${m.codigo}</div>
                    </td>
                    <td><span style="font-size:12px;">${m.operacao}</span></td>
                    <td><span class="code-badge" style="background:#EFF6FF; color:#1D4ED8; font-weight:700; font-size:12px;">${m.total_reciclagens_12m}× excessos</span></td>
                    <td><span class="rp ${m.faixa_risco}">${faixaLabel(m.faixa_risco)}</span></td>
                </tr>
            `).join('') || `<tr><td colspan="5" style="text-align:center; color:var(--c-muted); padding:16px">Nenhum registro encontrado para estes filtros.</td></tr>`;
        }

        renderChartMensal(mensal, ops);
        renderChartFaixas(faixas);
        renderChartOps(opsRank.slice(0, 8));

        // Carregar Relatório de IA
        loadRelatorioIA();
    } catch(e) { console.error('Painel:', e); }
}

async function loadRelatorioIA() {
    const ops = getMSSelected('ms-op');
    const meses = getMSSelected('ms-mes');
    const ano = val('p-ano') || val('k-ano');
    const container = document.getElementById('ai-report-body');
    if (!container) return;

    try {
        const q = `operacao=${enc(ops.join(','))}&ano=${enc(ano)}&mes=${enc(meses.join(','))}`;
        const res = await fetch(`/api/ia-relatorio-comparativo?${q}`);
        const r = await res.json();

        const varsHtml = (r.variacoes || []).map(v => {
            const isDown = v.variacao_pct < 0;
            const isUp   = v.variacao_pct > 0;
            const badgeColor = isDown ? '#10B981' : (isUp ? '#EF4444' : '#64748B');
            const icon = isDown ? '📉' : (isUp ? '📈' : '➡️');
            const pctTxt = isUp ? `+${v.variacao_pct}%` : `${v.variacao_pct}%`;
            return `
                <div style="background:#F1F5F9; padding:10px 14px; border-radius:6px; flex:1; min-width:130px; border-left:3px solid ${badgeColor}">
                    <div style="font-size:12px; color:var(--c-muted); font-weight:600;">${v.mes_nome}</div>
                    <div style="font-size:16px; font-weight:700; color:var(--c-text); margin:2px 0;">${v.total_eventos} reciclagens</div>
                    <div style="font-size:11.5px; color:${badgeColor}; font-weight:700;">
                        ${icon} ${v.variacao_pct === 0 ? 'Mês base' : pctTxt + ' vs mês anterior'}
                    </div>
                </div>
            `;
        }).join('');

        const recsHtml = (r.recomendacoes || []).map(rec => `<li style="margin-bottom:4px;">${rec}</li>`).join('');

        container.innerHTML = `
            <div style="display:flex; flex-direction:column; gap:14px;">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px; background:#EFF6FF; padding:12px 16px; border-radius:6px; border:1px solid #BFDBFE;">
                    <div>
                        <strong style="color:#1E40AF; font-size:13.5px;">${r.escopo || 'Análise Corporativa'}</strong>
                        <div style="font-size:12px; color:#1E3A8A; margin-top:2px;">Total de reciclagens no período: <strong>${r.total_acumulado}</strong> | Reincidentes: <strong>${r.reinc_acumulado}</strong></div>
                    </div>
                    <span style="font-size:13px; font-weight:700; color:#1D4ED8; background:#DBEAFE; padding:6px 12px; border-radius:20px;">
                        ${r.tendencia}
                    </span>
                </div>

                <div style="display:flex; gap:10px; flex-wrap:wrap;">
                    ${varsHtml}
                </div>

                <div style="background:#FFFFFF; border:1px solid #E2E8F0; padding:12px 16px; border-radius:6px;">
                    <strong style="color:var(--c-text); font-size:13px; display:block; margin-bottom:4px;">💡 Diagnóstico da Inteligência Artificial:</strong>
                    <p style="font-size:13px; color:var(--c-text); line-height:1.5; margin:0 0 10px 0;">${r.diagnostico}</p>
                    <strong style="color:var(--c-text); font-size:12.5px; display:block; margin-bottom:4px;">🎯 Recomendações Executivas:</strong>
                    <ul style="font-size:12.5px; color:var(--c-muted); margin:0; padding-left:18px;">
                        ${recsHtml}
                    </ul>
                </div>
            </div>
        `;
    } catch(e) {
        console.error('IA report:', e);
        container.innerHTML = `<div style="color:var(--c-red); font-size:13px; padding:10px;">❌ Erro ao carregar o relatório comparativo de IA.</div>`;
    }
}

function renderChartMensal(data, ops = []) {
    const ctx = document.getElementById('chartMensal');
    if (!ctx) return;
    if (_chartMensal) _chartMensal.destroy();

    let titleLabel = 'Total de Reciclagens';
    if (ops.length === 1) titleLabel = `Total de Reciclagens (${ops[0]})`;
    else if (ops.length > 1) titleLabel = `Total de Reciclagens (${ops.length} filiais)`;

    // Plugin inline para exibir rótulos sempre visíveis no topo de cada barra
    const datalabelPlugin = {
        id: 'barLabels',
        afterDatasetsDraw(chart) {
            const { ctx: c, data } = chart;
            chart.data.datasets.forEach((dataset, datasetIndex) => {
                const meta = chart.getDatasetMeta(datasetIndex);
                if (meta.hidden) return;
                meta.data.forEach((bar, index) => {
                    const value = dataset.data[index];
                    if (value === 0 || value == null) return;
                    c.save();
                    c.font = 'bold 11px Inter, sans-serif';
                    c.fillStyle = '#1E293B';
                    c.textAlign = 'center';
                    c.textBaseline = 'bottom';
                    c.fillText(value, bar.x, bar.y - 3);
                    c.restore();
                });
            });
        }
    };

    _chartMensal = new Chart(ctx, {
        type: 'bar',
        plugins: [datalabelPlugin],
        data: {
            labels: data.map(d => d.mes_nome),
            datasets: [
                {
                    label: titleLabel,
                    data: data.map(d => d.total_eventos),
                    backgroundColor: '#3B82F6',
                    borderRadius: 5
                },
                {
                    label: 'Motoristas Reincidentes',
                    data: data.map(d => d.reincidentes),
                    backgroundColor: '#EF4444',
                    borderRadius: 5
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: { padding: { top: 20 } },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: { font: { size: 11, weight: 'bold' }, boxWidth: 12 }
                },
                tooltip: {
                    callbacks: {
                        label: ctx => ` ${ctx.dataset.label}: ${ctx.parsed.y}`
                    }
                }
            },
            scales: {
                x: { grid: { display: false } },
                y: { beginAtZero: true, grid: { color: '#F0F4F8' } }
            }
        }
    });
}

function renderChartFaixas(data) {
    const ctx = document.getElementById('chartFaixas');
    if (!ctx) return;
    if (_chartFaixas) _chartFaixas.destroy();
    _chartFaixas = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Verde (Aderente)', 'Amarela (Atenção)', 'Laranja (Reincidente)', 'Vermelha (Crítico)'],
            datasets: [{
                data: [data.VERDE || 0, data.AMARELA || 0, data.LARANJA || 0, data.VERMELHA || 0],
                backgroundColor: ['#10B981', '#FBBF24', '#F97316', '#EF4444'],
                borderWidth: 0, hoverOffset: 6
            }]
        },
        options: {
            responsive: true, maintainAspectRatio: false, cutout: '65%',
            plugins: { legend: { position: 'bottom', labels: { font: { size: 11 }, boxWidth: 12 } } }
        }
    });
}

function renderChartOps(data) {
    const ctx = document.getElementById('chartOps');
    if (!ctx) return;
    if (_chartOps) _chartOps.destroy();
    _chartOps = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.map(d => d.operacao),
            datasets: [{
                label: 'Total de Reciclagens / Excessos Registrados',
                data: data.map(d => d.total_reciclagens),
                backgroundColor: '#0284C7',
                borderColor: '#0369A1',
                borderWidth: 1,
                borderRadius: 4
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            onClick: (e, activeElements) => {
                if (activeElements && activeElements.length > 0) {
                    const idx = activeElements[0].index;
                    const opSelected = data[idx].operacao;
                    setFilialFilterAndLoad(opSelected);
                }
            },
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: { font: { size: 11, weight: 'bold' }, boxWidth: 12 }
                },
                tooltip: {
                    callbacks: {
                        afterBody: () => '💡 Clique para filtrar todo o Painel por esta filial'
                    }
                }
            },
            scales: { x: { beginAtZero: true, grid: { color: '#F0F4F8' } }, y: { grid: { display: false } } }
        }
    });
}

function setFilialFilterAndLoad(opName) {
    setMSSelected('ms-op', opName ? [opName] : []);
    setMSSelected('ms-mes', []);

    // Mudar para aba do Painel se necessário
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.querySelector('[data-tab="painel"]')?.classList.add('active');
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.getElementById('tab-painel')?.classList.add('active');

    setText('page-title', 'Painel Executivo');
    setText('page-sub', opName ? `Visão de B.I. da Filial: ${opName}` : 'Programa corporativo de prevenção ao excesso de velocidade');

    loadPainel();
}

function resetPainelFilter() {
    setMSSelected('ms-op', []);
    setMSSelected('ms-mes', []);
    setVal('p-ano', '');
    loadPainel();
}

// ── Motoristas ────────────────────────────────────────────
let _mTimer = null;

function initFiltersListeners() {
    const kBusca = document.getElementById('k-busca');
    if (kBusca) {
        kBusca.addEventListener('input', () => {
            clearTimeout(_kTimer);
            _kTimer = setTimeout(loadKanban, 250);
        });
    }

    ['m-busca', 'm-op', 'm-faixa', 'm-nivel'].forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        el.addEventListener('input', () => {
            clearTimeout(_mTimer);
            _mTimer = setTimeout(loadMotoristas, 280);
        });
        el.addEventListener('change', loadMotoristas);
    });
    ['k-op', 'k-gestor', 'k-mes', 'k-ano'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('change', loadKanban);
    });

    const pOp = document.getElementById('p-op');
    if (pOp) pOp.addEventListener('change', loadPainel);
}

async function loadMotoristas() {
    const search  = val('m-busca');
    const operacao = val('m-op');
    const faixa   = val('m-faixa');
    const nivel   = val('m-nivel');
    const ano     = val('k-ano') || val('p-ano') || '';
    try {
        const r = await fetch(`/api/motoristas?search=${enc(search)}&operacao=${enc(operacao)}&faixa=${enc(faixa)}&nivel=${enc(nivel)}&ano=${enc(ano)}`);
        const drivers = await r.json();
        const tbody = document.getElementById('tbody-motoristas');
        if (!tbody) return;

        if (!drivers.length) {
            tbody.innerHTML = `<tr><td colspan="9" style="text-align:center;padding:24px;color:var(--c-muted)">Nenhum motorista encontrado.</td></tr>`;
            return;
        }

        tbody.innerHTML = drivers.map(d => {
            const situacao = d.situacao_pgsc || '1º Enquadramento';
            const consequencia = d.consequencia_pgsc || 'Reciclagem';
            const totalEventos = d.total_reciclagens_ano !== undefined ? d.total_reciclagens_ano : d.total_reciclagens_12m;

            return `
            <tr>
                <td><span class="code-badge">${d.codigo}</span></td>
                <td><strong>${d.nome}</strong></td>
                <td>${d.operacao}</td>
                <td>${d.gestor}</td>
                <td><span class="rp ${d.faixa_risco}">${faixaLabel(d.faixa_risco)}</span></td>
                <td><span class="lvl-badge" style="font-weight:700;">${situacao}</span></td>
                <td><span style="font-weight:700; color:#1D4ED8; background:#EFF6FF; padding:3px 8px; border-radius:4px; font-size:11.5px;">⚡ ${consequencia}</span></td>
                <td style="font-weight:700;text-align:center">${totalEventos}</td>
                <td><button class="btn-tiny" onclick="openProntuario('${d.codigo}')">🔍 Abrir Prontuário</button></td>
            </tr>
            `;
        }).join('');
    } catch(e) { console.error('Motoristas:', e); }
}

// ── Análise Mensal em Linhas ──────────────────────────────
async function loadMensal() {
    try {
        const r = await fetch('/api/comparativo-mensal');
        const data = await r.json();
        const tbody = document.getElementById('tbody-mensal-linhas');
        if (!tbody) return;

        const jan = data.find(d => d.mes_num === 1) || {};
        const fev = data.find(d => d.mes_num === 2) || {};
        const mar = data.find(d => d.mes_num === 3) || {};
        const abr = data.find(d => d.mes_num === 4) || {};

        const sumEvents = data.reduce((a, b) => a + (b.total_eventos || 0), 0);
        const sumUnicos = data.reduce((a, b) => a + (b.motoristas_unicos || 0), 0);
        const sumReinc  = data.reduce((a, b) => a + (b.reincidentes || 0), 0);

        tbody.innerHTML = `
            <tr>
                <td><strong>🚗 Motoristas Únicos Monitorados</strong></td>
                <td>${jan.motoristas_unicos || 0}</td>
                <td>${fev.motoristas_unicos || 0}</td>
                <td>${mar.motoristas_unicos || 0}</td>
                <td>${abr.motoristas_unicos || 0}</td>
                <td><strong>${sumUnicos}</strong></td>
            </tr>
            <tr>
                <td><strong>📋 Total de Reciclagens (Incidentes)</strong></td>
                <td><span class="code-badge">${jan.total_eventos || 0}</span></td>
                <td><span class="code-badge">${fev.total_eventos || 0}</span></td>
                <td><span class="code-badge">${mar.total_eventos || 0}</span></td>
                <td><span class="code-badge">${abr.total_eventos || 0}</span></td>
                <td><strong class="code-badge">${sumEvents}</strong></td>
            </tr>
            <tr>
                <td><strong>⚠️ Motoristas Reincidentes (2+ rec)</strong></td>
                <td style="color:var(--c-red);font-weight:700">${jan.reincidentes || 0}</td>
                <td style="color:var(--c-red);font-weight:700">${fev.reincidentes || 0}</td>
                <td style="color:var(--c-red);font-weight:700">${mar.reincidentes || 0}</td>
                <td style="color:var(--c-red);font-weight:700">${abr.reincidentes || 0}</td>
                <td style="color:var(--c-red);font-weight:700"><strong>${sumReinc}</strong></td>
            </tr>
            <tr>
                <td><strong>📊 Taxa de Reincidência (%)</strong></td>
                <td><strong>${jan.taxa_reincidencia || 0}%</strong></td>
                <td><strong>${fev.taxa_reincidencia || 0}%</strong></td>
                <td><strong>${mar.taxa_reincidencia || 0}%</strong></td>
                <td><strong>${abr.taxa_reincidencia || 0}%</strong></td>
                <td><strong>${sumUnicos ? (sumReinc / sumUnicos * 100).toFixed(1) : 0}%</strong></td>
            </tr>
        `;
    } catch(e) { console.error('Mensal:', e); }
}

// ── Operações ─────────────────────────────────────────────
async function loadOperacoes() {
    try {
        const r = await fetch('/api/ranking-operacoes');
        const ops = await r.json();

        const tOps = document.getElementById('tbody-ops');
        if (tOps) {
            tOps.innerHTML = ops.map((o, i) => `
                <tr style="cursor:pointer;" onclick="setFilialFilterAndLoad('${o.operacao}')" title="Clique para filtrar o Painel Executivo por ${o.operacao}">
                    <td><strong>#${i+1}</strong></td>
                    <td><strong style="color:var(--c-blue);text-decoration:underline;">${o.operacao}</strong></td>
                    <td style="color:var(--c-muted);font-weight:600;font-size:12px;">${o.gestor || '–'}</td>
                    <td><span class="code-badge">${o.total_reciclagens}</span></td>
                    <td>${o.total_motoristas}</td>
                    <td style="color:var(--c-red);font-weight:700">${o.total_reincidentes}</td>
                    <td><strong>${o.taxa_reincidencia}%</strong></td>
                </tr>
            `).join('');
        }
    } catch(e) { console.error('Operações:', e); }
}

// ── Efetividade (Fluxo completo + Aderência + Reincidência) ──
let _efetInit = false;

async function initEfetividadeFilters() {
    // popula uma única vez as listas de filtro reaproveitando as opções existentes
    if (_efetInit) return;
    try {
        const r = await fetch('/api/filters-options');
        const d = await r.json();
        const fill = (id, items, allLabel) => {
            const sel = document.getElementById(id);
            if (!sel) return;
            const cur = sel.value;
            sel.innerHTML = `<option value="">${allLabel}</option>`;
            (items || []).forEach(x => {
                const opt = document.createElement('option');
                opt.value = x; opt.textContent = x;
                if (String(x) === cur) opt.selected = true;
                sel.appendChild(opt);
            });
        };
        const isRestrictedRole = (d.user_role === 'OPERACAO' || d.user_role === 'TREINAMENTO');
        const defaultAllLabel = (isRestrictedRole && d.operacoes && d.operacoes.length > 1)
            ? `Todas as Minhas Operações (${d.operacoes.length})`
            : 'Todas as Operações';
        fill('ef-op', d.operacoes, defaultAllLabel);
        fill('ef-ano', d.anos, 'Todos os Anos');
        const selMes = document.getElementById('ef-mes');
        if (selMes) {
            selMes.innerHTML = '<option value="">Todos os Meses</option>';
            (d.meses || []).sort((a, b) => a - b).forEach(m => {
                const opt = document.createElement('option');
                opt.value = m; opt.textContent = MONTH_NAMES[m] || `Mês ${m}`;
                selMes.appendChild(opt);
            });
        }
        ['ef-op', 'ef-ano', 'ef-mes'].forEach(id => {
            document.getElementById(id)?.addEventListener('change', loadEfetividade);
        });
        _efetInit = true;
    } catch(e) { console.warn('Efetividade filtros:', e); }
}

function resetEfetividadeFilters() {
    ['ef-op', 'ef-ano', 'ef-mes'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
    loadEfetividade();
}

function efParams() {
    return `operacao=${enc(val('ef-op'))}&ano=${enc(val('ef-ano'))}&mes=${enc(val('ef-mes'))}`;
}

async function loadEfetividade() {
    try {
        const q = efParams();
        const [kpi, evolucao, reincidentes] = await Promise.all([
            fetch(`/api/efetividade-kpis?${q}`).then(r => r.json()),
            fetch(`/api/evolucao-efetividade?${q}`).then(r => r.json()),
            fetch(`/api/reincidentes?${q}&apenas_alerta=${document.getElementById('ef-apenas-alerta')?.checked ? 1 : 0}`).then(r => r.json())
        ]);

        // KPIs do fluxo
        setText('ef-necessitam', kpi.motoristas_necessitam_reciclagem ?? '–');
        setText('ef-indicados', kpi.indicados ?? '–');
        setText('ef-realizados', kpi.realizados ?? '–');
        setText('ef-pendentes', kpi.pendentes ?? '–');
        setText('ef-andamento-sub', `${kpi.em_andamento ?? 0} em andamento`);
        setText('ef-recusados', kpi.recusados ?? '–');
        setText('ef-aderencia', (kpi.taxa_aderencia ?? 0) + '%');
        setText('ef-reincidentes', kpi.reincidentes ?? '–');
        setText('ef-alerta', kpi.reincidentes_meses_consecutivos ?? '–');
        setText('ef-alerta-sub', `${kpi.limiar_meses_consecutivos ?? 3}+ meses consecutivos com evento${kpi.regra_reincidencia_ativa ? ' · regra ativa' : ' · regra não validada'}`);

        // Tag de escopo
        const tag = document.getElementById('ef-tag');
        if (tag) {
            let parts = [];
            if (val('ef-op')) parts.push(val('ef-op'));
            if (val('ef-mes')) parts.push(MONTH_NAMES[val('ef-mes')] || `Mês ${val('ef-mes')}`);
            if (val('ef-ano')) parts.push(val('ef-ano'));
            tag.innerHTML = parts.length
                ? `<span class="status-pulse"></span> ${parts.join(' · ')}`
                : '<span class="status-pulse"></span> Visão Consolidada';
        }

        renderEfComparativo(kpi.comparativo_periodo_anterior);
        renderEfMelhorPior(kpi);
        renderChartEfetMensal(evolucao.mensal || []);
        renderChartEfetReinc(evolucao.mensal || []);
        renderEfOps(kpi.por_operacao || [], kpi.melhor_operacao, kpi.pior_operacao);
        renderEfReincidentes(reincidentes);
    } catch(e) { console.error('Efetividade:', e); }
}

function renderEfComparativo(comp) {
    const rot = document.getElementById('ef-comp-rotulo');
    const col = document.getElementById('ef-comp-col');
    const tb = document.getElementById('tbody-ef-comparativo');
    if (!comp || !tb) return;
    if (rot) rot.textContent = `— comparativo com o ${comp.rotulo_anterior || 'período anterior'}`;
    if (col) col.textContent = (comp.rotulo_anterior || 'Período anterior').replace(/^./, c => c.toUpperCase());

    const a = comp.atual || {}, p = comp.anterior || {};
    const linha = (nome, atual, anterior, unid = '') => {
        const delta = (anterior && anterior !== 0)
            ? Math.round((atual - anterior) / Math.abs(anterior) * 1000) / 10
            : null;
        const cor = delta === null ? 'var(--c-muted)' : (delta <= 0 ? '#10B981' : '#EF4444');
        const txt = delta === null ? '—' : `${delta > 0 ? '+' : ''}${delta}%`;
        return `<tr>
            <td><strong>${nome}</strong></td>
            <td>${atual}${unid}</td>
            <td style="color:var(--c-muted)">${anterior}${unid}</td>
            <td style="color:${cor}; font-weight:700;">${txt}</td>
        </tr>`;
    };
    tb.innerHTML =
        linha('Motoristas que necessitam reciclagem', a.motoristas_necessitam ?? 0, p.motoristas_necessitam ?? 0) +
        linha('Indicados', a.indicados ?? 0, p.indicados ?? 0) +
        linha('Realizados', a.realizados ?? 0, p.realizados ?? 0) +
        linha('Taxa de Aderência', a.taxa_aderencia ?? 0, p.taxa_aderencia ?? 0, '%');
}

function renderEfMelhorPior(kpi) {
    const rot = document.getElementById('ef-ops-rotulo');
    if (rot) rot.textContent = '';
}

function renderEfOps(rows) {
    const tb = document.getElementById('tbody-ef-ops');
    if (!tb) return;
    tb.innerHTML = rows.map(o => `<tr>
        <td><strong>${o.operacao}</strong></td>
        <td>${o.motoristas_necessitam}</td>
        <td><span class="code-badge">${o.indicados}</span></td>
        <td style="font-weight:600;">${o.realizados}</td>
        <td style="font-weight:600;">${o.recusados}</td>
        <td><strong>${o.taxa_aderencia}%</strong></td>
    </tr>`).join('') || `<tr><td colspan="6" style="text-align:center; color:var(--c-muted); padding:16px;">Nenhum registro no período.</td></tr>`;
}

function _consequenciaFromReinc(totalReinc) {
    if (totalReinc <= 1) return { label: '1º Enquadramento', cor: '#1D4ED8', bg: '#EFF6FF' };
    if (totalReinc === 2) return { label: '1ª Reincidência — Reciclagem + Termo', cor: '#B45309', bg: '#FFFBEB' };
    if (totalReinc === 3) return { label: '2ª Reincidência — Viagem + PDI + Adv', cor: '#C2410C', bg: '#FFF7ED' };
    if (totalReinc === 4) return { label: '3ª Reincidência — Comitê + Suspensão', cor: '#B91C1C', bg: '#FEF2F2' };
    return { label: '4ª Reincidência — Avaliação Permanência', cor: '#7C3AED', bg: '#F5F3FF' };
}

function renderEfReincidentes(data) {
    const tb = document.getElementById('tbody-ef-reincidentes');
    if (!tb) return;

    const rows = data.motoristas || [];
    tb.innerHTML = rows.map(m => {
        const totalEventos = m.indicados || 0;
        const cons = _consequenciaFromReinc(totalEventos);
        return `
        <tr style="cursor:pointer;" onclick="openProntuario('${m.codigo}')" title="Ver prontuário de ${toTitleCase(m.nome)}">
            <td>
                <div style="font-weight:600; color:var(--c-text);">${toTitleCase(m.nome)} ${m.em_alerta_reincidencia ? '⚠️' : ''}</div>
                <div style="font-size:11px; color:var(--c-muted);">${m.codigo}</div>
            </td>
            <td style="font-size:12px;">${m.operacao}</td>
            <td><span class="code-badge">${m.indicados}</span></td>
            <td style="color:var(--c-red); font-weight:700;">${m.total_reincidencias}</td>
            <td style="font-size:11.5px;">${(m.meses_que_reincidiu || []).join(', ') || '—'}</td>
            <td><span style="font-size:11px; font-weight:700; color:${cons.cor}; background:${cons.bg}; padding:3px 8px; border-radius:20px;">${cons.label}</span></td>
            <td><button class="btn-tiny" onclick="event.stopPropagation(); openProntuario('${m.codigo}')">🔍 Ver</button></td>
        </tr>`;
    }).join('') || `<tr><td colspan="7" style="text-align:center; color:var(--c-muted); padding:16px;">Nenhum motorista reincidente no período.</td></tr>`;
}

function filtrarTabelaReincidentes(query) {
    const q = (query || '').toLowerCase().trim();
    document.querySelectorAll('#tbody-ef-reincidentes tr').forEach(row => {
        const text = row.textContent.toLowerCase();
        row.style.display = (!q || text.includes(q)) ? '' : 'none';
    });
}

function renderChartEfetMensal(data) {
    const ctx = document.getElementById('chartEfetMensal');
    if (!ctx) return;
    if (_chartEfetMensal) _chartEfetMensal.destroy();
    _chartEfetMensal = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.map(d => d.mes_nome),
            datasets: [
                {
                    label: 'Indicados',
                    data: data.map(d => d.indicados),
                    backgroundColor: '#FBBF24',
                    borderRadius: 5
                },
                {
                    label: 'Realizados',
                    data: data.map(d => d.realizados),
                    backgroundColor: '#10B981',
                    borderRadius: 5
                },
                {
                    type: 'line',
                    label: 'Aderência (%)',
                    data: data.map(d => d.taxa_aderencia),
                    borderColor: '#1D4ED8',
                    backgroundColor: '#1D4ED8',
                    yAxisID: 'y1',
                    tension: 0.3,
                    pointRadius: 4
                }
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                legend: { display: true, position: 'top', labels: { font: { size: 11, weight: 'bold' }, boxWidth: 12 } },
                tooltip: { callbacks: { label: c => ` ${c.dataset.label}: ${c.parsed.y}${c.dataset.yAxisID === 'y1' ? '%' : ''}` } }
            },
            scales: {
                x: { grid: { display: false } },
                y: { beginAtZero: true, grid: { color: '#F0F4F8' }, title: { display: true, text: 'Qtd.' } },
                y1: { beginAtZero: true, max: 100, position: 'right', grid: { display: false }, title: { display: true, text: 'Aderência (%)' } }
            }
        }
    });
}

function renderChartEfetReinc(data) {
    const ctx = document.getElementById('chartEfetReinc');
    if (!ctx) return;
    if (_chartEfetReinc) _chartEfetReinc.destroy();
    _chartEfetReinc = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.map(d => d.mes_nome),
            datasets: [
                {
                    label: 'Motoristas que necessitam reciclagem',
                    data: data.map(d => d.motoristas_necessitam),
                    backgroundColor: '#3B82F6',
                    borderRadius: 5
                },
                {
                    label: 'Reincidentes (evento em mês anterior)',
                    data: data.map(d => d.reincidentes),
                    backgroundColor: '#EF4444',
                    borderRadius: 5
                }
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: true, position: 'top', labels: { font: { size: 11, weight: 'bold' }, boxWidth: 12 } } },
            scales: { x: { grid: { display: false } }, y: { beginAtZero: true, grid: { color: '#F0F4F8' } } }
        }
    });
}

// ── Prontuário Modal ──────────────────────────────────────
async function openProntuario(codigo) {
    try {
        const r = await fetch(`/api/motorista/${codigo}`);
        const d = await r.json();
        if (!d || !d.motorista) return;
        const m = d.motorista;
        _currentDriverData = d;

        document.getElementById('modal-eyebrow').textContent = 'PRONTUÁRIO INDIVIDUAL DO MOTORISTA';
        document.getElementById('modal-title').textContent = `Caso #PGCSC-${m.codigo}`;

        const totalRec = (d.reciclagens || []).length;
        let situacao = "1º Enquadramento";
        let consequencia = "Reciclagem";
        let st = 1;

        if (totalRec <= 1) {
            situacao = "1º Enquadramento";
            consequencia = "Reciclagem";
            st = 1;
        } else if (totalRec === 2) {
            situacao = "1ª Reincidência";
            consequencia = "Reciclagem + Termo de Compromisso";
            st = 2;
        } else if (totalRec === 3) {
            situacao = "2ª Reincidência";
            consequencia = "Viagem Assistida + PDI + Advertência";
            st = 3;
        } else if (totalRec === 4) {
            situacao = "3ª Reincidência";
            consequencia = "Comitê Corporativo + Suspensão";
            st = 4;
        } else {
            situacao = "4ª Reincidência (12m/ano)";
            consequencia = "Avaliação de Permanência na Função";
            st = 5;
        }

        document.getElementById('driver-header').innerHTML = `
            <div class="dh-item"><span>Motorista</span><strong>${toTitleCase(m.nome)}</strong></div>
            <div class="dh-item"><span>Faixa de Risco</span><span class="rp ${m.faixa_risco}">${faixaLabel(m.faixa_risco)}</span></div>
            <div class="dh-item"><span>Situação PGSC</span><strong style="color:#1D4ED8;">${situacao}</strong></div>
            <div class="dh-item"><span>Consequência PGSC</span><strong style="color:#B91C1C;">${consequencia}</strong></div>
            <div class="dh-item"><span>Operação</span><strong>${m.operacao}</strong></div>
            <div class="dh-item"><span>Gestor</span><strong>${toTitleCase(m.gestor)}</strong></div>
        `;

        renderProntuarioHistorico(d);

        const btnApr = document.getElementById('btn-prontuario-aprovar');
        if (btnApr) {
            if (m.etapa_kanban === 'APROVADO') {
                btnApr.textContent = '✅ Motorista Concluído / Aprovado';
                btnApr.disabled = true;
                btnApr.style.opacity = '0.7';
                btnApr.style.cursor = 'default';
            } else {
                btnApr.textContent = '✅ Aprovar & Concluir Motorista';
                btnApr.disabled = false;
                btnApr.style.opacity = '1';
                btnApr.style.cursor = 'pointer';
            }
        }

        openModal('modal-prontuario');
    } catch(e) { console.error('Prontuário:', e); }
}

// ── Prontuário: Reincidência + Linha do Tempo Individual ──
function renderProntuarioHistorico(d) {
    const h = d.historico;
    const boxReinc = document.getElementById('prontuario-reincidencia');
    const boxTimeline = document.getElementById('prontuario-timeline');
    if (!h) {
        if (boxReinc) boxReinc.innerHTML = `<div style="color:var(--c-muted); font-size:13px;">Histórico de efetividade indisponível.</div>`;
        if (boxTimeline) boxTimeline.innerHTML = '';
        return;
    }

    const evo = h.evolucao_pos_reciclagem || {};
    const melhorouTxt = evo.melhorou === true
        ? '<span style="color:#10B981; font-weight:700;">✅ Sim — menos eventos após a reciclagem</span>'
        : (evo.melhorou === false
            ? '<span style="color:#EF4444; font-weight:700;">⚠️ Não — eventos continuam/após reciclagem</span>'
            : '<span style="color:var(--c-muted);">Sem reciclagem realizada ainda</span>');

    if (boxReinc) {
        boxReinc.innerHTML = `
            <div style="display:flex; gap:10px; flex-wrap:wrap;">
                <div style="background:#F1F5F9; padding:10px 14px; border-radius:6px; flex:1; min-width:130px; border-left:3px solid #EF4444;">
                    <div style="font-size:11.5px; color:var(--c-muted); font-weight:600;">Total de Reincidências</div>
                    <div style="font-size:18px; font-weight:800; color:var(--c-text);">${h.total_reincidencias}</div>
                    <div style="font-size:11px; color:var(--c-muted);">meses com evento após o 1º</div>
                </div>
                <div style="background:#F1F5F9; padding:10px 14px; border-radius:6px; flex:1; min-width:130px; border-left:3px solid #F97316;">
                    <div style="font-size:11.5px; color:var(--c-muted); font-weight:600;">Maior Sequência Consecutiva</div>
                    <div style="font-size:18px; font-weight:800; color:var(--c-text);">${h.maior_sequencia_meses_consecutivos} ${h.maior_sequencia_meses_consecutivos >= h.limiar_meses_consecutivos && h.total_registros >= 2 ? '⚠️' : ''}</div>
                    <div style="font-size:11px; color:var(--c-muted);">meses seguidos com evento</div>
                </div>
                <div style="background:#F1F5F9; padding:10px 14px; border-radius:6px; flex:1; min-width:130px; border-left:3px solid #10B981;">
                    <div style="font-size:11.5px; color:var(--c-muted); font-weight:600;">Melhorou após reciclagem?</div>
                    <div style="font-size:13px; font-weight:700; margin-top:4px;">${melhorouTxt}</div>
                    <div style="font-size:11px; color:var(--c-muted);">${evo.eventos_antes_da_reciclagem ?? 0} eventos antes · ${evo.eventos_apos_reciclagem ?? 0} depois</div>
                </div>
            </div>
        `;
    }

    if (boxTimeline) {
        const bucketIcon = b => ({ realizado: '✅', recusado: '🚫', em_andamento: '🕐', pendente: '⏳' }[b] || '⏳');
        const bucketCor = b => ({ realizado: '#10B981', recusado: '#EF4444', em_andamento: '#F59E0B', pendente: '#64748B' }[b] || '#64748B');
        const items = (h.timeline || []).map(t => {
            const det = [];
            if (t.data_indicacao) det.push(`📅 Indicação: ${t.data_indicacao}`);
            if (t.responsavel) det.push(`👤 Responsável: ${t.responsavel}`);
            if (t.data_realizacao) det.push(`✔️ Realização: ${t.data_realizacao}`);
            if (t.resultado) det.push(`📈 Resultado: ${t.resultado}`);
            if (t.motivo_recusa) det.push(`🚫 Motivo: ${t.motivo_recusa}`);
            if (t.instrutor) det.push(`🎓 Instrutor: ${t.instrutor}`);
            const recId = t.reciclagem_id || t.id || '';
            const clickable = recId ? `onclick="openModalEditarReciclagem(${recId})" style="cursor:pointer;"` : '';
            const editBadge = recId ? `<span style="font-size:10px; background:#EFF6FF; color:#1D4ED8; padding:2px 7px; border-radius:20px; margin-left:6px; font-weight:700;">✏️ Editar</span>` : '';
            return `
                <div ${clickable} style="display:flex; gap:12px; padding:8px 0; border-left:2px solid #E2E8F0; margin-left:8px; padding-left:16px; position:relative; border-radius:4px; transition:background 0.15s;" onmouseenter="this.style.background='rgba(59,130,246,0.04)'" onmouseleave="this.style.background='transparent'">
                    <div style="position:absolute; left:-7px; top:14px; width:12px; height:12px; border-radius:50%; background:${bucketCor(t.bucket)};"></div>
                    <div style="flex:1;">
                        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:6px;">
                            <strong style="font-size:13px;">${t.mes_nome}/${t.ano} — ${t.acao_corretiva || 'Evento de reciclagem'} ${t.reincidente_no_mes ? '<span style="font-size:11px; color:#EF4444; font-weight:700;">🔁 REINCIDÊNCIA</span>' : '<span style="font-size:11px; color:#10B981; font-weight:600;">1º evento</span>'}</strong>
                            <div style="display:flex; align-items:center; gap:6px;">
                                <span class="sp sp-${t.status}" style="font-size:11px;">${bucketIcon(t.bucket)} ${t.status}</span>
                                ${editBadge}
                            </div>
                        </div>
                        ${det.length ? `<div style="font-size:12px; color:var(--c-muted); margin-top:4px;">${det.join(' · ')}</div>` : ''}
                    </div>
                </div>`;
        }).join('');
        boxTimeline.innerHTML = items
            || `<div style="color:var(--c-muted); font-size:13px;">Nenhum evento registrado.</div>`;
    }
}

function openModalEditarReciclagem(recId) {
    if (!_currentDriverData || !_currentDriverData.motorista) return;
    const m = _currentDriverData.motorista;
    const recList = _currentDriverData.reciclagens || [];
    const r = recList.find(item => item.id === recId) || recList.slice(-1)[0] || {};

    setVal('e-codigo', m.codigo);
    setVal('e-rec-id', r.id || '');
    setVal('e-status', r.status || 'PENDENTE');
    setVal('e-data', r.data_realizacao || '');
    setVal('e-responsavel', r.responsavel || '');
    setVal('e-instrutor', r.instrutor || '');
    setVal('e-resultado', r.resultado || '');
    setVal('e-motivo', r.motivo_recusa || '');
    setVal('e-obs', r.observacao || '');
    toggleMotivoRecusaRow();

    const modalTitle = document.querySelector('#modal-editar .modal-title');
    if (modalTitle) {
        modalTitle.textContent = `✏️ Editar Reciclagem — Mês ${r.mes || ''} / ${r.ano || 2026} (${toTitleCase(m.nome)})`;
    }

    openModal('modal-editar');
}

function openModalEditarGeral() {
    if (!_currentDriverData || !_currentDriverData.motorista) return;
    const recList = _currentDriverData.reciclagens || [];
    const lastRec = recList.slice(-1)[0] || {};
    openModalEditarReciclagem(lastRec.id);
}

let _driverToApprove = null;

function btnAprovarMotoristaAction() {
    if (!_currentDriverData || !_currentDriverData.motorista) return;
    const m = _currentDriverData.motorista;
    _driverToApprove = m;

    const textEl = document.getElementById('confirm-aprovar-text');
    if (textEl) {
        textEl.innerHTML = `Deseja aprovar e concluir o processo do motorista <strong>${toTitleCase(m.nome)}</strong> (Código <strong>${m.codigo}</strong>)?`;
    }

    openModal('modal-confirm-aprovar');
}

async function executearAprovacaoMotorista() {
    if (!_driverToApprove) return;
    const m = _driverToApprove;
    const btn = document.getElementById('btn-confirm-aprovar-submit');

    try {
        if (btn) btn.disabled = true;

        const res = await fetch('/api/motorista/aprovar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ codigo: m.codigo })
        });
        const d = await res.json();
        if (btn) btn.disabled = false;

        if (d.success) {
            closeModal('modal-confirm-aprovar');
            closeModal('modal-prontuario');
            toast(`✅ Motorista ${toTitleCase(m.nome)} Aprovado e Concluído com sucesso!`);
            refreshAllViews();
        } else {
            toast('❌ Erro: ' + (d.error || 'Falha ao aprovar.'));
        }
    } catch(err) {
        if (btn) btn.disabled = false;
        toast('❌ Erro de conexão.');
    }
}

function toggleMotivoRecusaRow() {
    const st = (val('e-status') || '').toUpperCase();
    const row = document.getElementById('row-e-motivo');
    if (row) row.style.display = (st === 'RECUSADO' || st === 'CANCELADO') ? '' : 'none';
}

function initFormEditar() {
    document.getElementById('e-status')?.addEventListener('change', toggleMotivoRecusaRow);
    document.getElementById('form-editar')?.addEventListener('submit', async (e) => {
        e.preventDefault();
        const recId = val('e-rec-id');
        if (!recId) {
            toast('⚠️ Nenhuma reciclagem selecionada.');
            return;
        }
        try {
            const res = await fetch('/api/reciclagem/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    id:              recId,
                    status:          val('e-status'),
                    data_realizacao: val('e-data'),
                    instrutor:       val('e-instrutor'),
                    observacao:      val('e-obs'),
                    responsavel:     val('e-responsavel'),
                    resultado:       val('e-resultado'),
                    motivo_recusa:   val('e-motivo')
                })
            });
            const d = await res.json();
            if (!d.success) {
                toast('❌ Erro: ' + (d.error || 'Falha ao atualizar.'));
                return;
            }

            closeModal('modal-editar');
            toast('✅ Tratativa atualizada com sucesso!');

            // Reabrir prontuário atualizado sem fechar o modal pai
            const codigoAtual = _currentDriverData?.motorista?.codigo;
            if (codigoAtual) {
                await openProntuario(codigoAtual);
            }

            refreshAllViews();
        } catch(err) { toast('❌ Erro de conexão.'); }
    });
}

// ── Configurações: Regras de Reincidência & Premiação ─────
async function carregarRegras() {
    try {
        const r = await fetch('/api/config/regras');
        const d = await r.json();
        setVal('cfg-reinc-meses', d.reincidencia_meses_consecutivos ?? 3);
        setVal('cfg-reinc-pct', d.premiacao_percentual_impacto ?? 30);
        const a1 = document.getElementById('cfg-reinc-ativa');
        const a2 = document.getElementById('cfg-premio-ativa');
        if (a1) a1.checked = !!d.regra_reincidencia_ativa;
        if (a2) a2.checked = !!d.regra_premiacao_ativa;
    } catch(e) { console.warn('Regras:', e); }
}

async function salvarRegras() {
    try {
        const res = await fetch('/api/config/regras', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                reincidencia_meses_consecutivos: val('cfg-reinc-meses') || 3,
                premiacao_percentual_impacto:    val('cfg-reinc-pct') || 30,
                regra_reincidencia_ativa:        document.getElementById('cfg-reinc-ativa')?.checked ? '1' : '0',
                regra_premiacao_ativa:           document.getElementById('cfg-premio-ativa')?.checked ? '1' : '0'
            })
        });
        const d = await res.json();
        if (d.success) toast('✅ Regras salvas! ' + (d.regras?.validada === false ? 'Lembrete: regras ainda não validadas pelo comitê.' : ''));
        else toast('❌ Erro: ' + (d.error || 'Falha ao salvar regras.'));
    } catch(e) { toast('❌ Erro de conexão.'); }
}

function refreshAllViews() {
    loadKanban();
    loadHeaderKPIs();
    loadPainel();
    loadMotoristas();
    loadMensal();
    // Recarrega a aba de Efetividade apenas se estiver ativa
    if (document.getElementById('tab-efetividade')?.classList.contains('active')) {
        loadEfetividade();
    }
}

// ── Upload Planilha ───────────────────────────────────────
function initUpload() {
    const dz   = document.getElementById('drop-zone');
    const inp  = document.getElementById('file-input');
    if (!dz || !inp) return;

    ['dragenter','dragover','dragleave','drop'].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); e.stopPropagation(); }));
    ['dragenter','dragover'].forEach(ev => dz.addEventListener(ev, () => dz.classList.add('over')));
    ['dragleave','drop'].forEach(ev => dz.addEventListener(ev, () => dz.classList.remove('over')));

    dz.addEventListener('drop', e => {
        const files = e.dataTransfer?.files;
        if (files && files[0]) uploadFile(files[0]);
    });
    inp.addEventListener('change', () => { if (inp.files[0]) uploadFile(inp.files[0]); });
}

async function uploadFile(file) {
    if (!file.name.match(/\.xlsx?$/i)) {
        toast('❌ Selecione um arquivo .xlsx ou .xls');
        return;
    }

    const fb = document.getElementById('import-feedback');
    fb.className = 'import-feedback loading';
    fb.innerHTML = `⏳ Importando <strong>${file.name}</strong>… Aguarde.`;

    const fd = new FormData();
    fd.append('file', file);

    try {
        const res = await fetch('/api/importar-excel', { method: 'POST', body: fd });
        const d = await res.json();

        if (d.success) {
            const s = d.stats || {};
            fb.className = 'import-feedback ok';
            fb.innerHTML = `
                <strong style="display:block;margin-bottom:10px;font-size:14px">✅ Planilha importada com sucesso!</strong>
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:13px">
                    <div>📋 Linhas processadas: <strong>${s.total_linhas || 0}</strong></div>
                    <div>🆕 Novos registros inseridos: <strong style="color:#10B981">${s.novos_registros || 0}</strong></div>
                    <div>⏭️ Registros ignorados (já existiam): <strong style="color:#F97316">${s.ignorados || 0}</strong></div>
                    <div>🚗 Motoristas na planilha: <strong>${s.motoristas_afetados || 0}</strong></div>
                </div>
                ${(s.ignorados > 0) ? `<p style="margin-top:10px;font-size:12px;color:#F97316;">ℹ️ Os registros ignorados já estavam na base com edições manuais preservadas.</p>` : ''}
            `;
            refreshAllViews();
            loadFilterOptions();
        } else {
            fb.className = 'import-feedback err';
            fb.innerHTML = `❌ <strong>Erro ao importar:</strong> ${d.error}`;
        }
    } catch(err) {
        fb.className = 'import-feedback err';
        fb.innerHTML = '❌ Erro de conexão ao enviar planilha.';
    }
}

// ── Modal helpers ─────────────────────────────────────────
function openModal(id)  { document.getElementById(id)?.classList.add('open'); }
function closeModal(id) { document.getElementById(id)?.classList.remove('open'); }

function initOverlayClose() {
    document.querySelectorAll('.overlay').forEach(o => {
        o.addEventListener('click', e => { if (e.target === o) o.classList.remove('open'); });
    });
}

// ── Toast ─────────────────────────────────────────────────
function toast(msg, ms = 3000) {
    const t = document.getElementById('toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), ms);
}

// ── Utility ───────────────────────────────────────────────
function val(id)        { return document.getElementById(id)?.value || ''; }
function setVal(id, v)  { const e = document.getElementById(id); if (e) e.value = v; }
function setText(id, v) { const e = document.getElementById(id); if (e) e.textContent = v; }
function enc(s)         { return encodeURIComponent(s); }

// ── Configurações: Excluir Mês ────────────────────────────
let _cfgMesAno = null;

function abrirConfirmExcluirMes() {
    const mes = val('cfg-mes');
    const ano = val('cfg-ano');
    if (!mes || !ano) { toast('\u26a0\ufe0f Selecione o M\u00eas e o Ano antes de continuar.'); return; }

    const monthNames = {1:'Janeiro',2:'Fevereiro',3:'Mar\u00e7o',4:'Abril',5:'Maio',6:'Junho',
        7:'Julho',8:'Agosto',9:'Setembro',10:'Outubro',11:'Novembro',12:'Dezembro'};

    _cfgMesAno = { mes, ano };
    const txt = document.getElementById('confirm-excluir-mes-text');
    if (txt) txt.innerHTML = `Tem certeza que deseja excluir <strong>todas as reciclagens de ${monthNames[parseInt(mes)] || 'M\u00eas ' + mes} / ${ano}</strong>? Esta a\u00e7\u00e3o \u00e9 irrevers\u00edvel.`;
    openModal('modal-confirm-excluir-mes');
}

async function executarExcluirMes() {
    if (!_cfgMesAno) return;
    const btn = document.getElementById('btn-confirm-excluir-mes');
    if (btn) btn.disabled = true;
    try {
        const res = await fetch('/api/config/excluir-mes', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(_cfgMesAno)
        });
        const d = await res.json();
        if (btn) btn.disabled = false;
        if (d.success) {
            closeModal('modal-confirm-excluir-mes');
            toast(`\u2705 ${d.message}`);
            refreshAllViews();
            loadFilterOptions();
        } else { toast('\u274c Erro: ' + (d.error || 'Falha na opera\u00e7\u00e3o.')); }
    } catch(e) { if (btn) btn.disabled = false; toast('\u274c Erro de conex\u00e3o.'); }
}

// ── Configurações: Limpar Banco Total ─────────────────────
function abrirConfirmLimparTotal() {
    openModal('modal-confirm-limpar-banco');
}

async function executarLimparBanco() {
    const btn = document.getElementById('btn-confirm-limpar-banco');
    if (btn) btn.disabled = true;
    try {
        const res = await fetch('/api/config/limpar-banco', { method: 'POST' });
        const d = await res.json();
        if (btn) btn.disabled = false;
        if (d.success) {
            closeModal('modal-confirm-limpar-banco');
            toast('\u2705 Banco de dados limpo com sucesso! Importe uma nova planilha para come\u00e7ar.');
            refreshAllViews();
            loadFilterOptions();
        } else { toast('\u274c Erro: ' + (d.error || 'Falha na opera\u00e7\u00e3o.')); }
    } catch(e) { if (btn) btn.disabled = false; toast('\u274c Erro de conex\u00e3o.'); }
}


// ============================================================
// GESTÃO DE USUÁRIOS E PERMISSÕES (RBAC - APENAS MATRIZ)
// ============================================================

let _allUsersCache = [];
let _allOperationsCache = [];

async function loadUsuarios() {
    const tbody = document.getElementById('tbody-usuarios');
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; padding:28px; color:var(--c-muted);">Carregando usuários...</td></tr>';

    try {
        const res = await fetch('/api/admin/usuarios');
        if (!res.ok) {
            if (res.status === 403) {
                tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; padding:28px; color:var(--c-red);">Acesso restrito à Matriz.</td></tr>';
                return;
            }
            throw new Error('Falha ao carregar lista de usuários');
        }
        const users = await res.json();
        _allUsersCache = users || [];
        renderUsuariosTable(_allUsersCache);
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:28px; color:var(--c-red);">Erro: ${e.message}</td></tr>`;
    }
}

function formatPhoneBR(raw) {
    if (!raw) return '';
    const digits = String(raw).replace(/\D/g, '');
    let clean = digits;
    if (clean.startsWith('55') && clean.length > 10) clean = clean.slice(2);
    if (clean.length === 11) {
        return `(${clean.slice(0,2)}) ${clean.slice(2,7)}-${clean.slice(7)}`;
    } else if (clean.length === 10) {
        return `(${clean.slice(0,2)}) ${clean.slice(2,6)}-${clean.slice(6)}`;
    }
    return raw;
}

function escapeJsStr(str) {
    if (!str) return '';
    return String(str).replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function renderUsuariosTable(users) {
    const tbody = document.getElementById('tbody-usuarios');
    if (!tbody) return;
    if (!users || !users.length) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align:center; padding:28px; color:var(--c-muted);">Nenhum usuário cadastrado.</td></tr>';
        return;
    }

    tbody.innerHTML = users.map(u => {
        const isRoot = (u.email || '').toLowerCase() === 'matheuscamilio@expressonepomuceno.com.br';
        let roleBadge = '';
        if (u.role === 'MATRIZ') {
            roleBadge = '<span style="font-size:10.5px; font-weight:700; color:#1D4ED8; background:#EFF6FF; border:1px solid #BFDBFE; padding:3px 8px; border-radius:6px; letter-spacing:0.02em;">🏢 MATRIZ</span>';
        } else if (u.role === 'TREINAMENTO') {
            roleBadge = '<span style="font-size:10.5px; font-weight:700; color:#6B21A8; background:#F3E8FF; border:1px solid #D8B4FE; padding:3px 8px; border-radius:6px; letter-spacing:0.02em;">🎓 TREINAMENTO</span>';
        } else {
            roleBadge = '<span style="font-size:10.5px; font-weight:700; color:#047857; background:#ECFDF5; border:1px solid #A7F3D0; padding:3px 8px; border-radius:6px; letter-spacing:0.02em;">📍 OPERAÇÃO</span>';
        }

        let opDisplay = '';
        if (u.role === 'MATRIZ') {
            opDisplay = '<span style="color:var(--c-muted); font-size:12px; font-style:italic;">Todas as Operações</span>';
        } else {
            const rawOps = (u.operacao || '').split(',').map(s => s.trim()).filter(Boolean);
            if (!rawOps.length) {
                opDisplay = '<span style="color:var(--c-red); font-size:11px; font-weight:600; font-style:italic;">⚠️ Nenhuma vinculada</span>';
            } else if (rawOps.length === 1) {
                opDisplay = `<strong style="color:var(--c-text); font-size:12.5px; font-weight:700;">${rawOps[0]}</strong>`;
            } else {
                opDisplay = `
                    <div style="display:flex; flex-direction:column; gap:4px; max-width:280px;">
                        <span style="font-size:11px; font-weight:700; color:#1D4ED8;">${rawOps.length} filiais vinculadas:</span>
                        <div style="display:flex; flex-wrap:wrap; gap:3px;">
                            ${rawOps.map(op => `<span style="display:inline-block; font-size:10px; font-weight:700; color:#1E293B; background:#F1F5F9; border:1px solid #CBD5E1; padding:1px 6px; border-radius:4px;" title="${op}">${op}</span>`).join('')}
                        </div>
                    </div>
                `;
            }
        }

        const pwStatus = u.has_password
            ? '<span style="display:inline-flex; align-items:center; gap:4px; color:#15803D; background:#DCFCE7; border:1px solid #86EFAC; font-weight:700; font-size:11px; padding:2px 8px; border-radius:6px;">✓ Ativa</span>'
            : '<span style="display:inline-flex; align-items:center; gap:4px; color:#B45309; background:#FEF3C7; border:1px solid #FCD34D; font-weight:700; font-size:11px; padding:2px 8px; border-radius:6px;">⏳ Pendente</span>';

        const statusBadge = u.ativo
            ? '<span style="color:#15803D; background:#DCFCE7; border:1px solid #86EFAC; padding:2px 9px; border-radius:999px; font-size:11px; font-weight:700;">Ativo</span>'
            : '<span style="color:#B91C1C; background:#FEE2E2; border:1px solid #FCA5A5; padding:2px 9px; border-radius:999px; font-size:11px; font-weight:700;">Inativo</span>';

        const lastAccess = u.ultimo_acesso ? new Date(u.ultimo_acesso).toLocaleString('pt-BR') : '–';

        const phoneFormatted = formatPhoneBR(u.telefone);
        const phoneDisplay = u.telefone
            ? `<div style="display:inline-flex; align-items:center; gap:4px; font-size:11.5px; color:#059669; font-weight:600; margin-top:3px;">
                 <span>📱</span> <span>${phoneFormatted}</span>
               </div>`
            : `<div style="font-size:11px; color:var(--c-muted); font-style:italic; margin-top:2px;">Sem telefone</div>`;

        const actions = `
            <div style="display:flex; justify-content:flex-end; gap:6px; flex-wrap:wrap;">
                <button class="btn-ghost" onclick="abrirModalEditarUsuario(${u.id})" title="Editar dados, perfil e operações" style="padding:4px 8px; font-size:11px; font-weight:700; color:#2563EB; border-color:#BFDBFE; background:#EFF6FF;">✏️ Editar</button>
                <button class="btn-ghost" onclick="abrirModalWhatsapp(${u.id}, '${escapeJsStr(u.nome)}', '${escapeJsStr(u.email)}', '${escapeJsStr(u.telefone || '')}', '${escapeJsStr(u.operacao || '')}')" title="Gerenciar WhatsApp e Disparar Convite" style="padding:4px 8px; font-size:11px; font-weight:700; color:#059669; border-color:#A7F3D0; background:#ECFDF5;">📱 WhatsApp</button>
                <button class="btn-ghost" onclick="reenviarConvite(${u.id}, '${escapeJsStr(u.email)}')" title="Reenviar link para definir senha por e-mail" style="padding:4px 8px; font-size:11px; font-weight:600; color:#1D4ED8; border-color:#BFDBFE; background:#EFF6FF;">✉️ E-mail</button>
                ${isRoot ? '<span style="font-size:10px; color:var(--c-muted); font-weight:600; padding:4px 6px;">Root</span>' : `
                <button class="btn-ghost" onclick="toggleStatusUsuario(${u.id})" title="${u.ativo ? 'Desativar usuário' : 'Ativar usuário'}" style="padding:4px 8px; font-size:11px; font-weight:600; color:${u.ativo ? '#DC2626' : '#16A34A'}; border-color:${u.ativo ? '#FECACA' : '#BBF7D0'}; background:${u.ativo ? '#FEF2F2' : '#F0FDF4'};">
                    ${u.ativo ? 'Desativar' : 'Ativar'}
                </button>
                <button class="btn-ghost" onclick="excluirUsuario(${u.id}, '${escapeJsStr(u.nome)}')" title="Excluir usuário" style="padding:4px 8px; font-size:11px; color:#DC2626; border-color:#FECACA; background:#FEF2F2;">🗑️</button>
                `}
            </div>
        `;

        return `
            <tr>
                <td style="padding:12px 16px;"><strong style="color:var(--c-text); font-size:13px;">${u.nome}</strong></td>
                <td style="padding:12px 16px;">
                    <div style="font-family:'JetBrains Mono', monospace, sans-serif; font-size:12px; color:#334155; font-weight:500;">${u.email}</div>
                    ${phoneDisplay}
                </td>
                <td style="padding:12px 16px;">${roleBadge}</td>
                <td style="padding:12px 16px;">${opDisplay}</td>
                <td style="padding:12px 16px;">${pwStatus}</td>
                <td style="padding:12px 16px;">${statusBadge}</td>
                <td style="padding:12px 16px; font-size:12px; color:#475569;">${lastAccess}</td>
                <td style="padding:12px 16px; text-align:right;">${actions}</td>
            </tr>
        `;
    }).join('');
}

// ── OPERAÇÕES CHECKLIST MULTI-SELECT ──

async function ensureOperationsLoaded() {
    if (_allOperationsCache && _allOperationsCache.length) return _allOperationsCache;
    try {
        const res = await fetch('/api/admin/operacoes-lista');
        const ops = await res.json();
        _allOperationsCache = ops || [];
    } catch(e) {
        console.error('Erro ao carregar operacoes-lista:', e);
        _allOperationsCache = [];
    }
    return _allOperationsCache;
}

function renderOpsChecklist(type, selectedOps = []) {
    const containerId = (type === 'edit') ? 'edit-usr-ops-container' : 'usr-ops-container';
    const container = document.getElementById(containerId);
    if (!container) return;

    const ops = _allOperationsCache || [];
    if (!ops.length) {
        container.innerHTML = '<span style="font-size:11.5px; color:var(--c-muted); text-align:center; padding:8px;">Nenhuma operação encontrada no banco.</span>';
        updateOpsCount(type);
        return;
    }

    const selSet = new Set((selectedOps || []).map(o => String(o).trim().toUpperCase()));

    container.innerHTML = ops.map((op, idx) => {
        const isChecked = selSet.has(op.toUpperCase());
        const inputId = `chk-op-${type}-${idx}`;
        return `
            <label class="op-check-item chk-op-row-${type}" data-name="${op.toLowerCase()}" style="display:flex; align-items:center; gap:8px; padding:5px 8px; border-radius:4px; cursor:pointer; font-size:12px; user-select:none; background:${isChecked ? '#EFF6FF' : 'transparent'}; transition:background 0.12s;">
                <input type="checkbox" id="${inputId}" value="${op}" class="chk-usr-op-${type}" ${isChecked ? 'checked' : ''} onchange="onOpItemChecked('${type}', this)">
                <span style="font-weight:${isChecked ? '700' : '600'}; color:${isChecked ? '#1D4ED8' : '#334155'};">${op}</span>
            </label>
        `;
    }).join('');

    updateOpsCount(type);
}

function onOpItemChecked(type, checkbox) {
    const label = checkbox.closest('label');
    if (label) {
        if (checkbox.checked) {
            label.style.background = '#EFF6FF';
            const span = label.querySelector('span');
            if (span) { span.style.fontWeight = '700'; span.style.color = '#1D4ED8'; }
        } else {
            label.style.background = 'transparent';
            const span = label.querySelector('span');
            if (span) { span.style.fontWeight = '600'; span.style.color = '#334155'; }
        }
    }
    updateOpsCount(type);
}

function filterOpsList(type) {
    const inputId = (type === 'edit') ? 'edit-usr-op-search' : 'usr-op-search';
    const term = (document.getElementById(inputId)?.value || '').toLowerCase().trim();
    const rows = document.querySelectorAll(`.chk-op-row-${type}`);
    rows.forEach(r => {
        const name = r.dataset.name || '';
        r.style.display = (!term || name.includes(term)) ? 'flex' : 'none';
    });
}

function selectAllOps(type) {
    const rows = document.querySelectorAll(`.chk-op-row-${type}`);
    rows.forEach(r => {
        if (r.style.display !== 'none') {
            const chk = r.querySelector('input[type="checkbox"]');
            if (chk) {
                chk.checked = true;
                r.style.background = '#EFF6FF';
                const span = r.querySelector('span');
                if (span) { span.style.fontWeight = '700'; span.style.color = '#1D4ED8'; }
            }
        }
    });
    updateOpsCount(type);
}

function clearAllOps(type) {
    const chks = document.querySelectorAll(`.chk-usr-op-${type}`);
    chks.forEach(chk => {
        chk.checked = false;
        const label = chk.closest('label');
        if (label) {
            label.style.background = 'transparent';
            const span = label.querySelector('span');
            if (span) { span.style.fontWeight = '600'; span.style.color = '#334155'; }
        }
    });
    updateOpsCount(type);
}

function getSelectedOps(type) {
    const chks = document.querySelectorAll(`.chk-usr-op-${type}:checked`);
    return Array.from(chks).map(c => c.value.trim().toUpperCase());
}

function updateOpsCount(type) {
    const countEl = document.getElementById((type === 'edit') ? 'edit-usr-ops-count' : 'usr-ops-count');
    if (!countEl) return;
    const count = document.querySelectorAll(`.chk-usr-op-${type}:checked`).length;
    countEl.textContent = count === 1 ? '1 operação selecionada' : `${count} operações selecionadas`;
    countEl.style.color = count > 0 ? '#1D4ED8' : 'var(--c-muted)';
}

function toggleOperacaoSelect(type = 'novo') {
    const isEdit = (type === 'edit');
    const roleEl = document.getElementById(isEdit ? 'edit-usr-role' : 'usr-role');
    const groupEl = document.getElementById(isEdit ? 'group-edit-usr-operacao' : 'group-usr-operacao');
    const noticeEl = document.getElementById(isEdit ? 'notice-edit-matriz-operacao' : 'notice-novo-matriz-operacao');

    const role = (roleEl?.value || 'OPERACAO').toUpperCase();

    if (role === 'MATRIZ') {
        if (groupEl) groupEl.style.display = 'none';
        if (noticeEl) noticeEl.style.display = 'block';
    } else {
        if (groupEl) groupEl.style.display = 'block';
        if (noticeEl) noticeEl.style.display = 'none';
    }
}

// ── MODAL NOVO USUÁRIO ──

async function openModalNovoUsuario() {
    document.getElementById('form-novo-usuario')?.reset();
    const errEl = document.getElementById('novo-usr-error');
    if (errEl) errEl.style.display = 'none';

    const searchInput = document.getElementById('usr-op-search');
    if (searchInput) searchInput.value = '';

    await ensureOperationsLoaded();
    renderOpsChecklist('novo', []);
    toggleOperacaoSelect('novo');
    openModal('modal-novo-usuario');
}

async function handleSalvarNovoUsuario(e) {
    e.preventDefault();
    const nome = document.getElementById('usr-nome').value.trim();
    const email = document.getElementById('usr-email').value.trim();
    const telefone = (document.getElementById('usr-telefone')?.value || '').trim();
    const role = document.getElementById('usr-role').value;
    const selectedOps = getSelectedOps('novo');

    const btn = document.getElementById('btn-salvar-usr');
    const txt = document.getElementById('txt-salvar-usr');
    const spin = document.getElementById('spin-salvar-usr');
    const errEl = document.getElementById('novo-usr-error');

    if (errEl) errEl.style.display = 'none';

    if (role !== 'MATRIZ' && (!selectedOps || !selectedOps.length)) {
        if (errEl) {
            errEl.textContent = '⚠️ Selecione ao menos uma operação vinculada para este usuário.';
            errEl.style.display = 'block';
        }
        return;
    }

    if (btn) btn.disabled = true;
    if (txt) txt.style.display = 'none';
    if (spin) spin.style.display = 'inline-block';

    try {
        const res = await fetch('/api/admin/usuarios', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nome, email, telefone, role, operacao: selectedOps })
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Erro ao salvar usuário');
        }
        closeModal('modal-novo-usuario');
        showToast(data.message || 'Usuário cadastrado com sucesso!');
        loadUsuarios();
    } catch(err) {
        if (errEl) {
            errEl.textContent = '⚠️ ' + err.message;
            errEl.style.display = 'block';
        }
    } finally {
        if (btn) btn.disabled = false;
        if (txt) txt.style.display = 'inline';
        if (spin) spin.style.display = 'none';
    }
}

// ── MODAL EDITAR USUÁRIO ──

async function abrirModalEditarUsuario(userId) {
    const errEl = document.getElementById('edit-usr-error');
    if (errEl) errEl.style.display = 'none';

    let user = _allUsersCache.find(u => u.id === userId);
    if (!user) {
        try {
            const res = await fetch(`/api/admin/usuarios/${userId}`);
            if (res.ok) user = await res.json();
        } catch(e) {}
    }

    if (!user) {
        alert('Usuário não encontrado.');
        return;
    }

    const isRoot = (user.email || '').toLowerCase() === 'matheuscamilio@expressonepomuceno.com.br';

    document.getElementById('edit-usr-id').value = user.id;
    document.getElementById('edit-usr-nome').value = user.nome || '';
    document.getElementById('edit-usr-email').value = user.email || '';
    document.getElementById('edit-usr-telefone').value = formatPhoneBR(user.telefone) || '';
    document.getElementById('edit-usr-senha').value = '';

    const roleSel = document.getElementById('edit-usr-role');
    const rootNote = document.getElementById('edit-usr-root-note');
    if (roleSel) {
        roleSel.value = user.role || 'OPERACAO';
        if (isRoot) {
            roleSel.value = 'MATRIZ';
            roleSel.disabled = true;
            if (rootNote) rootNote.style.display = 'block';
        } else {
            roleSel.disabled = false;
            if (rootNote) rootNote.style.display = 'none';
        }
    }

    const searchInput = document.getElementById('edit-usr-op-search');
    if (searchInput) searchInput.value = '';

    await ensureOperationsLoaded();
    const userOps = (user.operacao || '').split(',').map(s => s.trim().toUpperCase()).filter(Boolean);
    renderOpsChecklist('edit', userOps);
    toggleOperacaoSelect('edit');

    openModal('modal-editar-usuario');
}

async function handleSalvarEdicaoUsuario(e) {
    e.preventDefault();
    const userId = document.getElementById('edit-usr-id').value;
    const nome = document.getElementById('edit-usr-nome').value.trim();
    const email = document.getElementById('edit-usr-email').value.trim();
    const telefone = (document.getElementById('edit-usr-telefone')?.value || '').trim();
    const roleSel = document.getElementById('edit-usr-role');
    const role = (roleSel ? roleSel.value : 'OPERACAO').toUpperCase();
    const novaSenha = (document.getElementById('edit-usr-senha')?.value || '').trim();
    const selectedOps = getSelectedOps('edit');

    const btn = document.getElementById('btn-salvar-edit-usr');
    const txt = document.getElementById('txt-salvar-edit-usr');
    const spin = document.getElementById('spin-salvar-edit-usr');
    const errEl = document.getElementById('edit-usr-error');

    if (errEl) errEl.style.display = 'none';

    if (role !== 'MATRIZ' && (!selectedOps || !selectedOps.length)) {
        if (errEl) {
            errEl.textContent = '⚠️ Selecione ao menos uma operação vinculada para este usuário.';
            errEl.style.display = 'block';
        }
        return;
    }

    if (novaSenha && novaSenha.length < 6) {
        if (errEl) {
            errEl.textContent = '⚠️ A nova senha deve conter no mínimo 6 caracteres.';
            errEl.style.display = 'block';
        }
        return;
    }

    if (btn) btn.disabled = true;
    if (txt) txt.style.display = 'none';
    if (spin) spin.style.display = 'inline-block';

    try {
        const payload = {
            nome,
            email,
            telefone,
            role,
            operacao: selectedOps
        };
        if (novaSenha) payload.nova_senha = novaSenha;

        const res = await fetch(`/api/admin/usuarios/${userId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Erro ao atualizar usuário');
        }

        closeModal('modal-editar-usuario');
        showToast(data.message || 'Usuário atualizado com sucesso!');
        loadUsuarios();
    } catch(err) {
        if (errEl) {
            errEl.textContent = '⚠️ ' + err.message;
            errEl.style.display = 'block';
        }
    } finally {
        if (btn) btn.disabled = false;
        if (txt) txt.style.display = 'inline';
        if (spin) spin.style.display = 'none';
    }
}

/* ═══ GESTÃO DO WHATSAPP DO USUÁRIO ═══ */
let _currentWaUser = null;

function abrirModalWhatsapp(id, nome, email, telefone, operacao) {
    _currentWaUser = { id, nome, email, telefone, operacao };
    document.getElementById('m-wa-userid').value = id;
    document.getElementById('m-wa-nome').textContent = nome;
    document.getElementById('m-wa-email').textContent = email;
    document.getElementById('m-wa-operacao').textContent = operacao || 'Matriz / Todas';
    document.getElementById('m-wa-telefone').value = telefone || '';
    
    const errEl = document.getElementById('m-wa-error');
    if (errEl) {
        errEl.textContent = '';
        errEl.style.display = 'none';
    }
    openModal('modal-whatsapp-usuario');
}

async function salvarApenasTelefone() {
    if (!_currentWaUser) return;
    const telInput = document.getElementById('m-wa-telefone');
    const tel = (telInput ? telInput.value : '').trim();
    const errEl = document.getElementById('m-wa-error');
    if (errEl) errEl.style.display = 'none';

    try {
        const res = await fetch(`/api/admin/usuarios/${_currentWaUser.id}/update-phone`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ telefone: tel })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Erro ao atualizar telefone');
        _currentWaUser.telefone = data.user ? data.user.telefone : tel;
        showToast('Telefone atualizado com sucesso!');
        loadUsuarios();
    } catch(err) {
        if (errEl) {
            errEl.textContent = '⚠️ ' + err.message;
            errEl.style.display = 'block';
        } else {
            alert(err.message);
        }
    }
}

async function executarDisparoRoboWhatsapp() {
    if (!_currentWaUser) return;
    const telInput = document.getElementById('m-wa-telefone');
    const tel = (telInput ? telInput.value : '').trim();
    const errEl = document.getElementById('m-wa-error');
    if (errEl) errEl.style.display = 'none';

    if (!tel) {
        if (errEl) {
            errEl.textContent = '⚠️ Informe o número de telefone com DDD antes de disparar.';
            errEl.style.display = 'block';
        }
        return;
    }

    const btn = document.getElementById('btn-wa-disparar');
    const txt = document.getElementById('txt-wa-disparar');
    const spin = document.getElementById('spin-wa-disparar');
    if (btn) btn.disabled = true;
    if (txt) txt.style.display = 'none';
    if (spin) spin.style.display = 'inline-block';

    try {
        const res = await fetch(`/api/admin/usuarios/${_currentWaUser.id}/send-whatsapp`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ telefone: tel })
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.error || 'Falha ao disparar mensagem via WhatsApp.');
        }

        // Sucesso: fecha modal de envio e exibe o modal com joinha!
        closeModal('modal-whatsapp-usuario');
        loadUsuarios();
        
        const joinhaTitle = document.getElementById('joinha-title');
        const joinhaDesc = document.getElementById('joinha-desc');
        if (joinhaTitle) joinhaTitle.textContent = 'Convite Enviado!';
        if (joinhaDesc) joinhaDesc.textContent = `A mensagem com o link de ativação foi transmitida com sucesso para o WhatsApp de ${_currentWaUser.nome}.`;
        openModal('modal-sucesso-joinha');
    } catch(err) {
        // Exibe o erro no estilo vermelho no próprio modal
        if (errEl) {
            errEl.textContent = '⚠️ ' + err.message;
            errEl.style.display = 'block';
        } else {
            alert(err.message);
        }
    } finally {
        if (btn) btn.disabled = false;
        if (txt) txt.style.display = 'inline';
        if (spin) spin.style.display = 'none';
    }
}

function abrirWebWhatsappManual() {
    if (!_currentWaUser) return;
    const telInput = document.getElementById('m-wa-telefone');
    const tel = (telInput ? telInput.value : '').replace(/\D/g, '');
    if (!tel) {
        alert('Por favor, informe o telefone antes de abrir no WhatsApp Web.');
        return;
    }
    let ddi = tel;
    if (ddi.length === 10 || ddi.length === 11) ddi = '55' + ddi;
    const primeiroNome = (_currentWaUser.nome || 'Colega').trim().split(' ')[0];
    const text = encodeURIComponent(`Olá, ${primeiroNome}! Segue o link de acesso ao sistema PGCSC Telemetria da Expresso Nepomuceno: https://decamservice.com/telemetria`);
    window.open(`https://wa.me/${ddi}?text=${text}`, '_blank');
}

async function reenviarConvite(userId, email) {
    if (!confirm(`Deseja gerar e reenviar um novo link de acesso por e-mail para ${email}?`)) return;
    try {
        const res = await fetch(`/api/admin/usuarios/${userId}/resend-invite`, { method: 'POST' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error);
        showToast(data.message || 'Link reenviado!');
    } catch(e) {
        alert('Erro ao reenviar link: ' + e.message);
    }
}

async function toggleStatusUsuario(userId) {
    try {
        const res = await fetch(`/api/admin/usuarios/${userId}/toggle-status`, { method: 'POST' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error);
        showToast(data.message);
        loadUsuarios();
    } catch(e) {
        alert('Erro: ' + e.message);
    }
}

async function excluirUsuario(userId, nome) {
    if (!confirm(`Tem certeza que deseja excluir o usuário "${nome}"? Esta ação cancela todas as sessões e acessos associados.`)) return;
    try {
        const res = await fetch(`/api/admin/usuarios/${userId}`, { method: 'DELETE' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error);
        showToast(data.message);
        loadUsuarios();
    } catch(e) {
        alert('Erro ao excluir: ' + e.message);
    }
}
