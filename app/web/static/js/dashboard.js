let categoryChartInstance = null;
let cashflowChartInstance = null;

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initCharts();
    initRealtimeSync();

    if (localStorage.getItem('open_workspace_settings_modal') === 'true') {
        openWorkspaceSettingsModal();
    }

    const inviteFor = localStorage.getItem('show_invite_modal_for');
    if (inviteFor) {
        localStorage.removeItem('show_invite_modal_for');
        setTimeout(() => {
            openShareModalForUser(inviteFor);
        }, 300);
    }
});

function switchTab(tabId) {
    const targetEl = document.getElementById(tabId);
    if (!targetEl) return;

    const tabButtons = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabButtons.forEach(b => b.classList.remove('active'));
    tabContents.forEach(c => c.classList.remove('active'));

    const activeBtn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);

    if (activeBtn) activeBtn.classList.add('active');
    targetEl.classList.add('active');

    try {
        localStorage.setItem('active_dashboard_tab', tabId);
        if (history.replaceState) {
            history.replaceState(null, null, '#' + tabId);
        }
    } catch (e) {
        console.error(e);
    }

    if (window.innerWidth <= 1024) {
        const sidebar = document.getElementById('appSidebar');
        const backdrop = document.getElementById('sidebarBackdrop');
        if (sidebar) sidebar.classList.remove('open');
        if (backdrop) backdrop.classList.remove('active');
    }

    if (tabId === 'tab-dashboard') {
        setTimeout(() => {
            initCharts();
        }, 50);
    }
}

function initTabs() {
    const tabButtons = document.querySelectorAll('.tab-btn');

    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const target = btn.dataset.tab;
            switchTab(target);
        });
    });

    // Determinar aba inicial a partir do hash da URL ou localStorage
    let targetTab = 'tab-dashboard';
    const hash = window.location.hash ? window.location.hash.replace('#', '') : '';
    const saved = localStorage.getItem('active_dashboard_tab');

    if (hash && document.getElementById(hash)) {
        targetTab = hash;
    } else if (saved && document.getElementById(saved)) {
        targetTab = saved;
    }

    switchTab(targetTab);
}


function initCharts() {
    // 1. Gráfico de Categorias (Doughnut)
    const catCanvas = document.getElementById('categoryChart');
    if (catCanvas && window.dashboardData) {
        const categories = window.dashboardData.category_breakdown || [];
        const labels = categories.map(c => c.name);
        const data = categories.map(c => c.total);
        const bgColors = categories.map(c => c.color || '#6366f1');

        const ctx = catCanvas.getContext('2d');
        if (categoryChartInstance) categoryChartInstance.destroy();

        categoryChartInstance = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels.length ? labels : ['Sem despesas'],
                datasets: [{
                    data: data.length ? data : [1],
                    backgroundColor: bgColors.length ? bgColors : ['#374151'],
                    borderWidth: 0,
                    hoverOffset: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: {
                            color: '#9ca3af',
                            font: { family: 'Outfit', size: 12 },
                            padding: 15
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const val = Number(context.raw) || 0;
                                return ' ' + val.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
                            }
                        }
                    }
                },
                cutout: '70%'
            }
        });
    }

    // 2. Gráfico de Fluxo de Caixa (Bar)
    const cashCanvas = document.getElementById('cashflowChart');
    if (cashCanvas && window.dashboardData) {
        const income = window.dashboardData.total_income || 0;
        const expense = window.dashboardData.total_expense || 0;

        const ctx = cashCanvas.getContext('2d');
        if (cashflowChartInstance) cashflowChartInstance.destroy();

        cashflowChartInstance = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: ['Receitas', 'Despesas', 'Saldo'],
                datasets: [{
                    data: [income, expense, (income - expense)],
                    backgroundColor: ['#10b981', '#f43f5e', '#6366f1'],
                    borderRadius: 8,
                    maxBarThickness: 45
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const val = Number(context.raw) || 0;
                                return ' ' + val.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: '#9ca3af', font: { family: 'Outfit' } }
                    },
                    y: {
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: {
                            color: '#9ca3af',
                            font: { family: 'Outfit' },
                            callback: function(value) {
                                return Number(value).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });
                            }
                        }
                    }
                }
            }
        });
    }
}

function switchWorkspaceFromWeb(selectEl) {
    const wsId = selectEl.value;
    const urlParams = new URLSearchParams(window.location.search);
    urlParams.set('workspace_id', wsId);
    window.location.search = urlParams.toString();
}

async function toggleItemFromWeb(itemId) {
    try {
        const res = await fetch(`/api/shopping/toggle/${itemId}`, { method: 'POST' });
        if (res.ok) {
            localStorage.setItem('active_dashboard_tab', 'tab-shopping');
            window.location.reload();
        }
    } catch (e) {
        console.error(e);
    }
}

async function markReminderPaid(remId) {
    try {
        const res = await fetch(`/api/reminders/pay/${remId}`, { method: 'POST' });
        if (res.ok) {
            localStorage.setItem('active_dashboard_tab', 'tab-reminders');
            window.location.reload();
        }
    } catch (e) {
        console.error(e);
    }
}

/* ========================================================
   GESTÃO DE CONTAS BANCÁRIAS (CRUD & ATIVAÇÃO/INATIVAÇÃO)
   ======================================================== */
function selectBankPreset(name, icon, color, type = 'checking') {
    const accName = document.getElementById('accName');
    const accIcon = document.getElementById('accIcon');
    const accColor = document.getElementById('accColor');
    const accType = document.getElementById('accType');

    if (accName) accName.value = name;
    if (accIcon) accIcon.value = icon;
    if (accColor) accColor.value = color;
    if (accType && type) accType.value = type;

    updateAccountPreview();
}

function selectAccountEmoji(emoji) {
    const accIcon = document.getElementById('accIcon');
    if (accIcon) {
        accIcon.value = emoji;
        updateAccountPreview();
    }
}

function updateAccountPreview() {
    const name = document.getElementById('accName')?.value.trim() || 'Nome da Conta';
    const icon = document.getElementById('accIcon')?.value.trim() || '🏦';
    const color = document.getElementById('accColor')?.value || '#6366f1';
    const typeSelect = document.getElementById('accType');
    const typeText = typeSelect?.options[typeSelect.selectedIndex]?.text || 'Conta Corrente';

    const prevCard = document.getElementById('accPreviewCard');
    const prevIcon = document.getElementById('accPreviewIcon');
    const prevName = document.getElementById('accPreviewName');
    const prevType = document.getElementById('accPreviewType');
    const prevColor = document.getElementById('accPreviewColorBadge');

    if (prevCard) prevCard.style.borderLeftColor = color;
    if (prevIcon) prevIcon.textContent = icon;
    if (prevName) prevName.textContent = name;
    if (prevType) prevType.textContent = typeText.toUpperCase();
    if (prevColor) prevColor.style.background = color;
}

function openCreateAccountModal(wsId = null) {
    const title = document.getElementById('accountModalTitle');
    if (title) title.textContent = '➕ Nova Conta / Banco';
    const btn = document.getElementById('accSubmitBtn');
    if (btn) btn.textContent = 'Cadastrar Conta';
    const accId = document.getElementById('accId');
    if (accId) accId.value = '';
    const accName = document.getElementById('accName');
    if (accName) accName.value = '';
    const accType = document.getElementById('accType');
    if (accType) accType.value = 'checking';
    const accIcon = document.getElementById('accIcon');
    if (accIcon) accIcon.value = '🏦';
    const accColor = document.getElementById('accColor');
    if (accColor) accColor.value = '#6366f1';
    const accInitialBalance = document.getElementById('accInitialBalance');
    if (accInitialBalance) accInitialBalance.value = '0.00';
    const accActiveGroup = document.getElementById('accActiveGroup');
    if (accActiveGroup) accActiveGroup.style.display = 'none';
    const accIsActive = document.getElementById('accIsActive');
    if (accIsActive) accIsActive.checked = true;

    if (wsId) {
        const wsInput = document.getElementById('accWorkspaceId');
        if (wsInput) wsInput.value = wsId;
    }

    updateAccountPreview();

    const modal = document.getElementById('accountModal');
    if (modal) {
        modal.style.display = 'flex';
        modal.classList.add('show');
    }
}

function openEditAccountModal(id, name, type, initialBalance, icon, color, isActive) {
    const title = document.getElementById('accountModalTitle');
    if (title) title.textContent = '✏️ Editar Conta / Banco';
    const btn = document.getElementById('accSubmitBtn');
    if (btn) btn.textContent = 'Salvar Alterações';
    const accId = document.getElementById('accId');
    if (accId) accId.value = id;
    const accName = document.getElementById('accName');
    if (accName) accName.value = name;
    const accType = document.getElementById('accType');
    if (accType) accType.value = type || 'checking';
    const accIcon = document.getElementById('accIcon');
    if (accIcon) accIcon.value = icon || '🏦';
    const accColor = document.getElementById('accColor');
    if (accColor) accColor.value = color || '#6366f1';
    const accInitialBalance = document.getElementById('accInitialBalance');
    if (accInitialBalance) accInitialBalance.value = Number(initialBalance || 0).toFixed(2);
    const accActiveGroup = document.getElementById('accActiveGroup');
    if (accActiveGroup) accActiveGroup.style.display = 'block';
    const accIsActive = document.getElementById('accIsActive');
    if (accIsActive) accIsActive.checked = (isActive !== false && isActive !== 'false');

    updateAccountPreview();

    const modal = document.getElementById('accountModal');
    if (modal) {
        modal.style.display = 'flex';
        modal.classList.add('show');
    }
}

function closeAccountModal() {
    const modal = document.getElementById('accountModal');
    if (modal) {
        modal.style.display = 'none';
        modal.classList.remove('show');
    }
}

async function saveAccountForm(e) {
    if (e) e.preventDefault();
    const id = document.getElementById('accId')?.value;
    
    let workspaceId = parseInt(document.getElementById('accWorkspaceId')?.value, 10);
    if (!workspaceId || isNaN(workspaceId)) {
        const urlParams = new URLSearchParams(window.location.search);
        workspaceId = parseInt(urlParams.get('workspace_id'), 10);
    }
    if (!workspaceId || isNaN(workspaceId)) {
        workspaceId = parseInt(document.getElementById('usrWorkspaceId')?.value, 10);
    }

    const nameInput = document.getElementById('accName');
    const name = nameInput ? nameInput.value.trim() : '';
    const type = document.getElementById('accType')?.value || 'checking';
    const icon = document.getElementById('accIcon')?.value.trim() || '🏦';
    const color = document.getElementById('accColor')?.value || '#6366f1';
    const initBalInput = document.getElementById('accInitialBalance');
    const initialBalance = initBalInput ? (parseFloat(initBalInput.value) || 0.0) : 0.0;
    const isActive = document.getElementById('accIsActive')?.checked ?? true;

    if (!name) {
        alert('Por favor, informe o nome da conta.');
        return;
    }

    const submitBtn = document.getElementById('accSubmitBtn');
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Salvando...';
    }

    try {
        if (id) {
            // Edição (PUT)
            const res = await fetch(`/api/accounts/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name,
                    type: type,
                    icon: icon,
                    color: color,
                    initial_balance: initialBalance,
                    is_active: isActive
                })
            });
            const data = await res.json();
            if (res.ok && data.success) {
                localStorage.setItem('active_dashboard_tab', 'tab-accounts');
                window.location.reload();
            } else {
                const errMsg = typeof data.detail === 'string' ? data.detail : (data.message || 'Erro ao atualizar conta.');
                alert(errMsg);
            }
        } else {
            // Criação (POST)
            const payload = {
                name: name,
                type: type,
                icon: icon,
                color: color,
                initial_balance: initialBalance
            };
            if (workspaceId && !isNaN(workspaceId)) {
                payload.workspace_id = workspaceId;
            }

            const res = await fetch('/api/accounts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (res.ok && data.success) {
                localStorage.setItem('active_dashboard_tab', 'tab-accounts');
                window.location.reload();
            } else {
                let errMsg = 'Erro ao cadastrar conta.';
                if (typeof data.detail === 'string') errMsg = data.detail;
                else if (Array.isArray(data.detail)) errMsg = data.detail.map(d => d.msg || d).join(', ');
                else if (data.message) errMsg = data.message;
                alert(errMsg);
            }
        }
    } catch (err) {
        console.error(err);
        alert('Erro de comunicação com o servidor ao salvar conta.');
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = id ? 'Salvar Alterações' : 'Cadastrar Conta';
        }
    }
}

async function toggleAccountActive(accId) {
    try {
        const res = await fetch(`/api/accounts/${accId}/toggle-active`, { method: 'POST' });
        if (res.ok) {
            localStorage.setItem('active_dashboard_tab', 'tab-accounts');
            window.location.reload();
        } else {
            alert('Erro ao alterar status da conta.');
        }
    } catch (e) {
        console.error(e);
    }
}

async function deleteAccount(accId, name) {
    if (!confirm(`Deseja realmente excluir a conta "${name}"?\nOs lançamentos vinculados a ela não serão apagados, mas ficarão desvinculados.`)) {
        return;
    }

    try {
        const res = await fetch(`/api/accounts/${accId}`, { method: 'DELETE' });
        if (res.ok) {
            localStorage.setItem('active_dashboard_tab', 'tab-accounts');
            window.location.reload();
        } else {
            alert('Erro ao excluir conta.');
        }
    } catch (e) {
        console.error(e);
    }
}

async function confirmZeroAccount(accId, name, year = null, month = null) {
    const wsId = document.getElementById('usrWorkspaceId')?.value || 
                 new URLSearchParams(window.location.search).get('workspace_id') || 
                 document.getElementById('editTxWorkspaceId')?.value || 
                 '1';
                 
    const monthLabel = year && month ? `${String(month).padStart(2, '0')}/${year}` : 'neste mês';

    if (!confirm(`⚠️ Deseja realmente ZERAR as movimentações da conta "${name}" em ${monthLabel}?\n\nIsso removerá as transações vinculadas a esta conta no mês selecionado e recalculará o saldo.`)) {
        return;
    }

    try {
        let url = `/api/accounts/${accId}/zero?workspace_id=${wsId}`;
        if (year && month) {
            url += `&year=${year}&month=${month}`;
        }
        const res = await fetch(url, { method: 'POST' });
        const data = await res.json();
        if (res.ok && data.success) {
            alert(data.message || 'Conta zerada com sucesso!');
            localStorage.setItem('active_dashboard_tab', 'tab-accounts');
            window.location.reload();
        } else {
            alert(data.detail || data.message || 'Erro ao zerar conta.');
        }
    } catch (e) {
        console.error(e);
        alert('Erro de comunicação ao zerar conta.');
    }
}

async function confirmZeroMonth(wsId, monthLabel, year = null, month = null) {
    if (!confirm(`🚨 ATENÇÃO: Deseja realmente ZERAR TODOS OS LANÇAMENTOS do mês "${monthLabel}"?\n\nTodas as receitas e despesas deste mês serão excluídas e os saldos recalculados. Esta ação não pode ser desfeita!`)) {
        return;
    }

    try {
        let url = `/api/workspaces/${wsId}/zero-month`;
        if (year && month) {
            url += `?year=${year}&month=${month}`;
        }
        const res = await fetch(url, { method: 'POST' });
        const data = await res.json();
        if (res.ok && data.success) {
            alert(data.message || 'Mês zerado com sucesso!');
            localStorage.setItem('active_dashboard_tab', 'tab-transactions');
            window.location.reload();
        } else {
            alert(data.detail || data.message || 'Erro ao zerar mês.');
        }
    } catch (e) {
        console.error(e);
        alert('Erro de comunicação ao zerar mês.');
    }
}

/* ========================================================
   TRANSFERÊNCIA ENTRE CONTAS E CARTEIRAS
   ======================================================== */
function openTransferModal(fromAccId = null, toAccId = null) {
    const modal = document.getElementById('transferModal');
    if (!modal) return;

    const fromSelect = document.getElementById('transferFromAccount');
    const toSelect = document.getElementById('transferToAccount');
    const amountInput = document.getElementById('transferAmount');
    const dateInput = document.getElementById('transferDate');
    const descInput = document.getElementById('transferDescription');

    if (amountInput) amountInput.value = '';
    if (descInput) descInput.value = '';
    if (dateInput) {
        dateInput.value = new Date().toISOString().split('T')[0];
    }
    if (fromSelect && fromAccId) fromSelect.value = fromAccId;
    if (toSelect && toAccId) toSelect.value = toAccId;

    modal.style.display = 'flex';
    modal.classList.add('show');
    setTimeout(() => {
        if (amountInput) amountInput.focus();
    }, 100);
}

function closeTransferModal() {
    const modal = document.getElementById('transferModal');
    if (modal) {
        modal.style.display = 'none';
        modal.classList.remove('show');
    }
}

async function saveTransferForm(e) {
    if (e) e.preventDefault();

    const workspaceId = parseInt(document.getElementById('transferWorkspaceId').value, 10);
    const userId = parseInt(document.getElementById('transferUserId').value, 10) || 1;
    const fromAccountId = parseInt(document.getElementById('transferFromAccount').value, 10);
    const toAccountId = parseInt(document.getElementById('transferToAccount').value, 10);
    const amount = parseFloat(document.getElementById('transferAmount').value);
    const date = document.getElementById('transferDate').value;
    const description = document.getElementById('transferDescription').value.trim();

    if (!fromAccountId || !toAccountId) {
        alert('Por favor, selecione as contas de origem e destino.');
        return;
    }

    if (fromAccountId === toAccountId) {
        alert('A conta de origem e a conta de destino não podem ser iguais.');
        return;
    }

    if (!amount || amount <= 0) {
        alert('Por favor, informe um valor válido maior que zero.');
        return;
    }

    const submitBtn = document.getElementById('transferSubmitBtn');
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Transferindo...';
    }

    try {
        const res = await fetch('/api/accounts/transfer', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                workspace_id: workspaceId,
                user_id: userId,
                from_account_id: fromAccountId,
                to_account_id: toAccountId,
                amount: amount,
                description: description || 'Transferência entre contas',
                date: date || null
            })
        });

        if (res.ok) {
            closeTransferModal();
            // Mantém na aba atual ou vai para extrato
            const currentTab = localStorage.getItem('active_dashboard_tab') || 'tab-accounts';
            localStorage.setItem('active_dashboard_tab', currentTab);
            window.location.reload();
        } else {
            const err = await res.json();
            alert(err.detail || 'Erro ao realizar transferência.');
        }
    } catch (err) {
        console.error(err);
        alert('Erro de comunicação com o servidor.');
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Confirmar Transferência 🔄';
        }
    }
}

/* ========================================================
   GESTÃO DE TRANSAÇÕES (EXCLUSÃO UNITÁRIA E EM LOTE)
   ======================================================== */
function toggleSelectAllTx(master) {
    const checkboxes = document.querySelectorAll('.tx-checkbox');
    checkboxes.forEach(cb => cb.checked = master.checked);
    updateSelectedTxCount();
}

function updateSelectedTxCount() {
    const checked = document.querySelectorAll('.tx-checkbox:checked');
    const count = checked.length;
    const toolbar = document.getElementById('batchActionToolbar');
    const countEl = document.getElementById('selectedCount');
    const master = document.getElementById('selectAllTx');

    if (countEl) countEl.textContent = count;
    if (toolbar) {
        toolbar.style.display = count > 0 ? 'flex' : 'none';
    }

    const all = document.querySelectorAll('.tx-checkbox');
    if (master && all.length > 0) {
        master.checked = (checked.length === all.length);
    }
}

async function deleteSingleTransaction(txId) {
    if (!confirm('Deseja realmente excluir este lançamento?\nO saldo da conta vinculada será estornado automaticamente.')) {
        return;
    }

    try {
        const res = await fetch(`/api/transactions/${txId}`, { method: 'DELETE' });
        if (res.ok) {
            localStorage.setItem('active_dashboard_tab', 'tab-transactions');
            window.location.reload();
        } else {
            alert('Erro ao excluir lançamento.');
        }
    } catch (e) {
        console.error(e);
        alert('Erro ao se comunicar com o servidor.');
    }
}

async function deleteSelectedTransactions() {
    const checked = document.querySelectorAll('.tx-checkbox:checked');
    const ids = Array.from(checked).map(cb => parseInt(cb.value, 10));

    if (ids.length === 0) return;

    if (!confirm(`Deseja excluir os ${ids.length} lançamentos selecionados?\nOs saldos das contas bancárias vinculadas serão estornados automaticamente.`)) {
        return;
    }

    try {
        const res = await fetch('/api/transactions/delete-batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ transaction_ids: ids })
        });
        if (res.ok) {
            localStorage.setItem('active_dashboard_tab', 'tab-transactions');
            window.location.reload();
        } else {
            alert('Erro ao excluir lançamentos em lote.');
        }
    } catch (e) {
        console.error(e);
        alert('Erro de comunicação com o servidor.');
    }
}

/* ========================================================
   GESTÃO DE PERFIS / CONTAS / WORKSPACES (CONFIGURAÇÃO)
   ======================================================== */
function openWorkspaceSettingsModal(subtab = null) {
    hideWorkspaceForm();
    hideUserForm();
    const modal = document.getElementById('workspaceSettingsModal');
    if (modal) {
        modal.style.display = 'flex';
        modal.classList.add('show');
        localStorage.setItem('open_workspace_settings_modal', 'true');
        const activeSubtab = subtab || localStorage.getItem('active_config_subtab') || 'profiles';
        switchConfigSubTab(activeSubtab);
    }
}

function closeWorkspaceSettingsModal() {
    const modal = document.getElementById('workspaceSettingsModal');
    if (modal) {
        modal.style.display = 'none';
        modal.classList.remove('show');
        localStorage.removeItem('open_workspace_settings_modal');
    }
}

function switchConfigSubTab(tabName) {
    localStorage.setItem('active_config_subtab', tabName);

    const secProfiles = document.getElementById('config-section-profiles');
    const secUsers = document.getElementById('config-section-users');
    const secTokens = document.getElementById('config-section-tokens');
    
    const btnProfiles = document.getElementById('btn-config-profiles');
    const btnUsers = document.getElementById('btn-config-users');
    const btnTokens = document.getElementById('btn-config-tokens');

    // Reset all tabs
    if (secProfiles) secProfiles.style.display = 'none';
    if (secUsers) secUsers.style.display = 'none';
    if (secTokens) secTokens.style.display = 'none';

    const inactiveBtn = (btn) => {
        if (!btn) return;
        btn.style.background = 'transparent';
        btn.style.color = 'var(--text-secondary)';
        btn.style.borderColor = 'transparent';
    };

    const activeBtn = (btn) => {
        if (!btn) return;
        btn.style.background = 'var(--primary)';
        btn.style.color = '#fff';
        btn.style.borderColor = 'var(--primary)';
    };

    inactiveBtn(btnProfiles);
    inactiveBtn(btnUsers);
    inactiveBtn(btnTokens);

    if (tabName === 'users') {
        if (secUsers) secUsers.style.display = 'flex';
        activeBtn(btnUsers);
    } else if (tabName === 'tokens') {
        if (secTokens) secTokens.style.display = 'flex';
        activeBtn(btnTokens);
        loadSystemTokens();
    } else {
        if (secProfiles) secProfiles.style.display = 'flex';
        activeBtn(btnProfiles);
    }
}

/* ========================================================
   GESTÃO DE USUÁRIOS & MEMBROS (WEB & TELEGRAM)
   ======================================================== */
function toggleNewUserForm() {
    const form = document.getElementById('userMemberForm');
    if (form) {
        if (form.style.display === 'none' || !form.style.display) {
            document.getElementById('usrFormTitle').textContent = '➕ Adicionar Novo Usuário';
            document.getElementById('usrSubmitBtn').textContent = 'Cadastrar Usuário';
            document.getElementById('usrUserId').value = '';
            document.getElementById('usrNameInput').value = '';
            document.getElementById('usrTelegramInput').value = '';
            document.getElementById('usrRoleInput').value = 'member';
            document.getElementById('usrIsActive').checked = true;
            form.style.display = 'block';
            document.getElementById('usrNameInput').focus();
        } else {
            form.style.display = 'none';
        }
    }
}

function hideUserForm() {
    const form = document.getElementById('userMemberForm');
    if (form) form.style.display = 'none';
}

function openEditUserForm(userId, name, username, telegramId, role, isActive) {
    const form = document.getElementById('userMemberForm');
    if (form) {
        document.getElementById('usrFormTitle').textContent = '✏️ Editar Usuário / Membro';
        document.getElementById('usrSubmitBtn').textContent = 'Salvar Alterações';
        document.getElementById('usrUserId').value = userId;
        document.getElementById('usrNameInput').value = name;
        
        let tgVal = username ? `@${username}` : (telegramId || '');
        if (tgVal.startsWith('pending_user_') || tgVal.startsWith('user_')) {
            tgVal = '';
        }
        document.getElementById('usrTelegramInput').value = tgVal;
        document.getElementById('usrRoleInput').value = role || 'member';
        document.getElementById('usrIsActive').checked = isActive;
        
        form.style.display = 'block';
        document.getElementById('usrNameInput').focus();
    }
}

async function saveUserForm(e) {
    e.preventDefault();
    const userId = document.getElementById('usrUserId').value;
    const workspaceId = parseInt(document.getElementById('usrWorkspaceId').value, 10);
    const name = document.getElementById('usrNameInput').value.trim();
    const telegramInput = document.getElementById('usrTelegramInput').value.trim();
    const role = document.getElementById('usrRoleInput').value;
    const isActive = document.getElementById('usrIsActive').checked;

    if (!name) {
        alert('Por favor, informe o nome do usuário.');
        return;
    }

    let username = null;
    let telegramId = null;
    if (telegramInput) {
        if (telegramInput.startsWith('@')) {
            username = telegramInput.substring(1);
        } else if (/^\d+$/.test(telegramInput)) {
            telegramId = telegramInput;
        } else {
            username = telegramInput;
        }
    }

    const submitBtn = document.getElementById('usrSubmitBtn');
    if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Salvando...';
    }

    try {
        localStorage.setItem('open_workspace_settings_modal', 'true');
        localStorage.setItem('active_config_subtab', 'users');

        if (userId) {
            // Edição (PUT)
            const res = await fetch(`/api/users/${userId}?workspace_id=${workspaceId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name,
                    username: username,
                    telegram_id: telegramId,
                    role: role,
                    is_active: isActive
                })
            });
            if (res.ok) {
                window.location.reload();
            } else {
                const err = await res.json();
                alert(err.detail || 'Erro ao atualizar usuário.');
            }
        } else {
            // Criação (POST)
            localStorage.setItem('show_invite_modal_for', name);
            const res = await fetch('/api/users', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    workspace_id: workspaceId,
                    name: name,
                    username: username,
                    telegram_id: telegramId,
                    role: role,
                    is_active: isActive
                })
            });
            if (res.ok) {
                window.location.reload();
            } else {
                localStorage.removeItem('show_invite_modal_for');
                const err = await res.json();
                alert(err.detail || 'Erro ao adicionar usuário.');
            }
        }
    } catch (err) {
        console.error(err);
        alert('Erro de comunicação com o servidor.');
    } finally {
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Salvar Usuário & Gerar Convite';
        }
    }
}

function copyInviteLink(link) {
    if (!link) {
        const input = document.getElementById('shareInviteLinkInput');
        link = input ? input.value : '';
    }
    if (navigator.clipboard && link) {
        navigator.clipboard.writeText(link).then(() => {
            alert('✅ Link de convite copiado para a área de transferência!\n\nEnvie para o usuário no WhatsApp ou Telegram.');
        }).catch(() => {
            prompt('Copie o link de convite abaixo:', link);
        });
    } else if (link) {
        prompt('Copie o link de convite abaixo:', link);
    }
}

function copyInviteLinkFromInput() {
    const input = document.getElementById('shareInviteLinkInput');
    const copyBtnText = document.getElementById('copyBtnText');
    if (input) {
        input.select();
        navigator.clipboard.writeText(input.value).then(() => {
            if (copyBtnText) copyBtnText.textContent = 'Copiado! ✅';
            setTimeout(() => {
                if (copyBtnText) copyBtnText.textContent = 'Copiar';
            }, 2000);
        }).catch(() => {
            prompt('Copie o link de convite:', input.value);
        });
    }
}

function shareViaWhatsApp(workspaceName, link, recipientName) {
    const greeting = recipientName ? `Olá ${recipientName}! ` : 'Olá! ';
    const text = `${greeting}Você foi convidado(a) para acessar nosso controle financeiro "${workspaceName}"!\n\n👉 Acesse pelo Telegram clicando no link abaixo:\n${link}\n\nLá você pode registrar gastos por mensagem de texto, áudio de voz ou foto de comprovantes!`;
    const url = `https://api.whatsapp.com/send?text=${encodeURIComponent(text)}`;
    window.open(url, '_blank');
}

function shareViaTelegram(workspaceName, link, recipientName) {
    const greeting = recipientName ? `Olá ${recipientName}! ` : 'Olá! ';
    const text = `${greeting}Acesse nosso controle financeiro "${workspaceName}" no Telegram:`;
    const url = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`;
    window.open(url, '_blank');
}

function shareModalViaWhatsApp(workspaceName) {
    const recipientName = document.getElementById('shareTargetName')?.textContent || '';
    const input = document.getElementById('shareInviteLinkInput');
    const link = input ? input.value : '';
    shareViaWhatsApp(workspaceName, link, recipientName);
}

function shareModalViaTelegram(workspaceName) {
    const recipientName = document.getElementById('shareTargetName')?.textContent || '';
    const input = document.getElementById('shareInviteLinkInput');
    const link = input ? input.value : '';
    shareViaTelegram(workspaceName, link, recipientName);
}

function openShareModalForUser(userName, link) {
    const nameEl = document.getElementById('shareTargetName');
    if (nameEl) nameEl.textContent = userName || 'o novo usuário';
    if (link) {
        const linkInput = document.getElementById('shareInviteLinkInput');
        if (linkInput) linkInput.value = link;
    }
    const modal = document.getElementById('shareInviteModal');
    if (modal) modal.style.display = 'flex';
}

function closeShareInviteModal() {
    const modal = document.getElementById('shareInviteModal');
    if (modal) modal.style.display = 'none';
}

async function toggleUserActive(userId) {
    const workspaceId = window.currentWorkspaceId;
    try {
        localStorage.setItem('open_workspace_settings_modal', 'true');
        localStorage.setItem('active_config_subtab', 'users');
        const res = await fetch(`/api/users/${userId}/toggle-active?workspace_id=${workspaceId}`, { method: 'POST' });
        if (res.ok) {
            window.location.reload();
        } else {
            alert('Erro ao alterar status do usuário.');
        }
    } catch (err) {
        console.error(err);
    }
}

async function removeWorkspaceUser(userId, name) {
    if (!confirm(`Deseja realmente remover o acesso de "${name}" deste perfil financeiro?`)) {
        return;
    }

    const workspaceId = window.currentWorkspaceId;
    try {
        localStorage.setItem('open_workspace_settings_modal', 'true');
        localStorage.setItem('active_config_subtab', 'users');
        const res = await fetch(`/api/workspaces/${workspaceId}/members/${userId}`, { method: 'DELETE' });
        if (res.ok) {
            window.location.reload();
        } else {
            const err = await res.json();
            alert(err.detail || 'Erro ao remover usuário.');
        }
    } catch (err) {
        console.error(err);
    }
}


function toggleNewWorkspaceForm() {
    const form = document.getElementById('workspaceForm');
    if (form) {
        if (form.style.display === 'none' || !form.style.display) {
            document.getElementById('wsFormTitle').textContent = '➕ Criar Novo Perfil';
            document.getElementById('wsSubmitBtn').textContent = 'Cadastrar Perfil';
            document.getElementById('wsId').value = '';
            document.getElementById('wsNameInput').value = '';
            document.getElementById('wsTypeInput').value = 'personal';
            form.style.display = 'block';
            document.getElementById('wsNameInput').focus();
        } else {
            form.style.display = 'none';
        }
    }
}

function openEditWorkspaceForm(id, name, type) {
    const form = document.getElementById('workspaceForm');
    if (form) {
        document.getElementById('wsFormTitle').textContent = '✏️ Editar Perfil / Conta';
        document.getElementById('wsSubmitBtn').textContent = 'Salvar Alterações';
        document.getElementById('wsId').value = id;
        document.getElementById('wsNameInput').value = name;
        document.getElementById('wsTypeInput').value = type || 'personal';
        form.style.display = 'block';
        document.getElementById('wsNameInput').focus();
    }
}

function hideWorkspaceForm() {
    const form = document.getElementById('workspaceForm');
    if (form) form.style.display = 'none';
}

function switchToWorkspace(wsId) {
    localStorage.removeItem('open_workspace_settings_modal');
    const urlParams = new URLSearchParams(window.location.search);
    urlParams.set('workspace_id', wsId);
    window.location.search = urlParams.toString();
}

async function saveWorkspaceForm(e) {
    e.preventDefault();
    const id = document.getElementById('wsId').value;
    const userId = parseInt(document.getElementById('wsUserId').value, 10) || 1;
    const name = document.getElementById('wsNameInput').value.trim();
    const type = document.getElementById('wsTypeInput').value;

    if (!name) {
        alert('Por favor, informe o nome do perfil.');
        return;
    }

    try {
        localStorage.setItem('open_workspace_settings_modal', 'true');
        if (id) {
            // Edição (PUT)
            const res = await fetch(`/api/workspaces/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: name, type: type })
            });
            if (res.ok) {
                window.location.reload();
            } else {
                const err = await res.json();
                alert(err.detail || 'Erro ao atualizar perfil.');
            }
        } else {
            // Criação (POST)
            const res = await fetch('/api/workspaces', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    name: name,
                    type: type,
                    user_id: userId
                })
            });
            if (res.ok) {
                window.location.reload();
            } else {
                const err = await res.json();
                alert(err.detail || 'Erro ao cadastrar perfil.');
            }
        }
    } catch (err) {
        console.error(err);
        alert('Erro de comunicação com o servidor.');
    }
}

async function deleteWorkspace(wsId, name) {
    if (!confirm(`Deseja realmente excluir o perfil "${name}"?\nATENÇÃO: Todos os lançamentos, contas e registros vinculados a este perfil serão permanentemente removidos!`)) {
        return;
    }

    try {
        localStorage.setItem('open_workspace_settings_modal', 'true');
        const res = await fetch(`/api/workspaces/${wsId}`, { method: 'DELETE' });
        if (res.ok) {
            // Se estava no workspace apagado, remove o param da URL para carregar outro
            const urlParams = new URLSearchParams(window.location.search);
            if (urlParams.get('workspace_id') == wsId) {
                urlParams.delete('workspace_id');
                window.location.search = urlParams.toString();
            } else {
                window.location.reload();
            }
        } else {
            const err = await res.json();
            alert(err.detail || 'Erro ao excluir perfil.');
        }
    } catch (e) {
        console.error(e);
        alert('Erro de comunicação com o servidor.');
    }
}

/* ========================================================
   FILTRAGEM E EXCLUSÃO GERAL (TRANSAÇÕES, METAS, ETC)
   ======================================================== */
function filterTransactionsTable(query) {
    const q = (query || '').toLowerCase().trim();
    const rows = document.querySelectorAll('.tx-row-item');

    rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        if (!q || text.includes(q)) {
            row.style.display = '';
        } else {
            row.style.display = 'none';
        }
    });
}

async function deleteReminder(reminderId, title) {
    if (!confirm(`Deseja excluir o lembrete "${title}"?`)) return;

    try {
        const res = await fetch(`/api/reminders/${reminderId}`, { method: 'DELETE' });
        if (res.ok) {
            localStorage.setItem('active_dashboard_tab', 'tab-reminders');
            window.location.reload();
        } else {
            alert('Erro ao excluir lembrete.');
        }
    } catch (e) {
        console.error(e);
        alert('Erro ao se comunicar com o servidor.');
    }
}

async function deleteGoal(goalId, title) {
    if (!confirm(`Deseja excluir a meta "${title}"?`)) return;

    try {
        const res = await fetch(`/api/goals/${goalId}`, { method: 'DELETE' });
        if (res.ok) {
            localStorage.setItem('active_dashboard_tab', 'tab-goals');
            window.location.reload();
        } else {
            alert('Erro ao excluir meta.');
        }
    } catch (e) {
        console.error(e);
        alert('Erro ao se comunicar com o servidor.');
    }
}

async function deleteVehicleMaintenance(mId, desc) {
    if (!confirm(`Deseja excluir o registro veicular "${desc}"?`)) return;

    try {
        const res = await fetch(`/api/vehicles/maintenance/${mId}`, { method: 'DELETE' });
        if (res.ok) {
            localStorage.setItem('active_dashboard_tab', 'tab-vehicles');
            window.location.reload();
        } else {
            alert('Erro ao excluir registro de manutenção.');
        }
    } catch (e) {
        console.error(e);
        alert('Erro ao se comunicar com o servidor.');
    }
}

async function deleteShoppingItem(itemId, name) {
    if (!confirm(`Deseja excluir o item "${name}" da lista de mercado?`)) return;

    try {
        const res = await fetch(`/api/shopping/item/${itemId}`, { method: 'DELETE' });
        if (res.ok) {
            localStorage.setItem('active_dashboard_tab', 'tab-shopping');
            window.location.reload();
        } else {
            alert('Erro ao excluir item de mercado.');
        }
    } catch (e) {
        console.error(e);
        alert('Erro ao se comunicar com o servidor.');
    }
}

/* ========================================================
   SINCRONIZAÇÃO EM TEMPO REAL (SSE + WEBSOCKET + POLLING)
   ======================================================== */
let sseSource = null;
let currentDataVersion = 0;
let isReloading = false;

function initRealtimeSync() {
    const wsId = window.currentWorkspaceId;
    if (!wsId) return;

    // 1. Inicia Server-Sent Events (SSE) nativo
    connectSSE(wsId);

    // 2. Polling de fallback leve a cada 3.5s
    setInterval(() => {
        checkVersionPolling(wsId);
    }, 3500);
}

function connectSSE(wsId) {
    if (!window.EventSource) return;

    try {
        if (sseSource) {
            sseSource.close();
        }

        sseSource = new EventSource(`/api/events/${wsId}`);

        sseSource.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.event === 'connected') {
                    currentDataVersion = data.version || 0;
                } else if (data.event === 'data_updated' || data.event === 'reload') {
                    triggerLiveReload();
                }
            } catch (e) {}
        };

        sseSource.onerror = () => {
            // EventSource tenta reconectar automaticamente
        };
    } catch (err) {
        console.warn('SSE indisponível:', err);
    }
}

let currentDataFingerprint = null;

async function checkVersionPolling(wsId) {
    if (isReloading) return;
    try {
        const res = await fetch(`/api/sync/version?workspace_id=${wsId}`);
        if (res.ok) {
            const data = await res.json();
            if (currentDataFingerprint === null) {
                currentDataFingerprint = data.fingerprint;
                currentDataVersion = data.version;
            } else if ((data.fingerprint && data.fingerprint !== currentDataFingerprint) || (data.version && data.version > currentDataVersion)) {
                currentDataFingerprint = data.fingerprint;
                currentDataVersion = data.version;
                triggerLiveReload();
            }
        }
    } catch (e) {}
}

function triggerLiveReload() {
    if (isReloading) return;
    // Não recarrega se o usuário estiver ativamente digitando em algum formulário
    const activeEl = document.activeElement;
    if (activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.tagName === 'SELECT')) {
        return;
    }

    isReloading = true;
    window.location.reload();
}

/* ========================================================
   GESTÃO DE TOKENS & CONEXÕES (TELEGRAM & GEMINI IA)
   ======================================================== */

function toggleTokenVisibility(inputId, iconId) {
    const input = document.getElementById(inputId);
    const icon = document.getElementById(iconId);
    if (!input) return;
    if (input.type === 'password') {
        input.type = 'text';
        if (icon) icon.textContent = '🙈';
    } else {
        input.type = 'password';
        if (icon) icon.textContent = '👁️';
    }
}

async function loadSystemTokens() {
    const tgBadge = document.getElementById('telegramStatusBadge');
    const gemBadge = document.getElementById('geminiStatusBadge');
    const tgInput = document.getElementById('cfgTelegramToken');
    const gemInput = document.getElementById('cfgGeminiKey');

    try {
        const res = await fetch('/api/system/tokens');
        if (res.ok) {
            const data = await res.json();
            
            if (tgInput) tgInput.value = data.telegram_token_raw || '';
            if (gemInput) gemInput.value = data.gemini_key_raw || '';

            if (tgBadge) {
                if (data.has_telegram) {
                    tgBadge.textContent = '🟢 Configurado (' + (data.telegram_token_masked || 'Ativo') + ')';
                    tgBadge.style.background = 'rgba(16, 185, 129, 0.15)';
                    tgBadge.style.color = '#34d399';
                } else {
                    tgBadge.textContent = '🟡 Não Configurado';
                    tgBadge.style.background = 'rgba(245, 158, 11, 0.15)';
                    tgBadge.style.color = '#fbbf24';
                }
            }

            if (gemBadge) {
                if (data.has_gemini) {
                    gemBadge.textContent = '🟢 IA Ativa (' + (data.gemini_key_masked || 'Ativo') + ')';
                    gemBadge.style.background = 'rgba(99, 102, 241, 0.15)';
                    gemBadge.style.color = '#818cf8';
                } else {
                    gemBadge.textContent = '🟡 Chave Padrão / Inativa';
                    gemBadge.style.background = 'rgba(245, 158, 11, 0.15)';
                    gemBadge.style.color = '#fbbf24';
                }
            }
        }
    } catch (e) {
        console.error('Erro ao carregar tokens:', e);
    }
}

async function testTelegramConnection() {
    const tgInput = document.getElementById('cfgTelegramToken');
    const resultBox = document.getElementById('telegramTestResult');
    const btn = document.getElementById('btnTestTelegram');
    
    const token = tgInput ? tgInput.value.trim() : '';
    if (!token) {
        alert('Por favor, insira o Token do Telegram antes de testar.');
        return;
    }

    if (btn) btn.disabled = true;
    if (resultBox) {
        resultBox.style.display = 'block';
        resultBox.style.background = 'rgba(255,255,255,0.05)';
        resultBox.style.color = 'var(--text-secondary)';
        resultBox.innerHTML = '⏳ Testando conexão com a API do Telegram...';
    }

    try {
        const res = await fetch('/api/system/test-telegram', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: token })
        });
        const data = await res.json();
        
        if (resultBox) {
            if (data.success) {
                resultBox.style.background = 'rgba(16, 185, 129, 0.15)';
                resultBox.style.color = '#34d399';
                resultBox.style.border = '1px solid rgba(16, 185, 129, 0.3)';
                resultBox.innerHTML = '✅ <b>Sucesso!</b> ' + (data.message || 'Bot conectado.') + (data.bot_username ? ` (@${data.bot_username})` : '');
            } else {
                resultBox.style.background = 'rgba(239, 68, 68, 0.15)';
                resultBox.style.color = '#f87171';
                resultBox.style.border = '1px solid rgba(239, 68, 68, 0.3)';
                resultBox.innerHTML = '❌ <b>Falha:</b> ' + (data.message || 'Token inválido.');
            }
        }
    } catch (e) {
        if (resultBox) {
            resultBox.style.background = 'rgba(239, 68, 68, 0.15)';
            resultBox.style.color = '#f87171';
            resultBox.innerHTML = '❌ Erro de comunicação com o servidor.';
        }
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function testGeminiConnection() {
    const gemInput = document.getElementById('cfgGeminiKey');
    const resultBox = document.getElementById('geminiTestResult');
    const btn = document.getElementById('btnTestGemini');
    
    const key = gemInput ? gemInput.value.trim() : '';
    if (!key) {
        alert('Por favor, insira a Chave do Gemini antes de testar.');
        return;
    }

    if (btn) btn.disabled = true;
    if (resultBox) {
        resultBox.style.display = 'block';
        resultBox.style.background = 'rgba(255,255,255,0.05)';
        resultBox.style.color = 'var(--text-secondary)';
        resultBox.innerHTML = '⏳ Testando chave com a API Google Gemini...';
    }

    try {
        const res = await fetch('/api/system/test-gemini', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: key })
        });
        const data = await res.json();
        
        if (resultBox) {
            if (data.success) {
                resultBox.style.background = 'rgba(99, 102, 241, 0.15)';
                resultBox.style.color = '#a78bfa';
                resultBox.style.border = '1px solid rgba(99, 102, 241, 0.3)';
                resultBox.innerHTML = '✅ <b>Sucesso!</b> ' + (data.message || 'Chave válida.') + (data.sample_models ? `<br><small style="color:var(--text-muted)">Modelos: ${data.sample_models.join(', ')}</small>` : '');
            } else {
                resultBox.style.background = 'rgba(239, 68, 68, 0.15)';
                resultBox.style.color = '#f87171';
                resultBox.style.border = '1px solid rgba(239, 68, 68, 0.3)';
                resultBox.innerHTML = '❌ <b>Falha:</b> ' + (data.message || 'Chave inválida.');
            }
        }
    } catch (e) {
        if (resultBox) {
            resultBox.style.background = 'rgba(239, 68, 68, 0.15)';
            resultBox.style.color = '#f87171';
            resultBox.innerHTML = '❌ Erro de comunicação com o servidor.';
        }
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function saveSystemTokens(e) {
    if (e) e.preventDefault();
    const tgInput = document.getElementById('cfgTelegramToken');
    const gemInput = document.getElementById('cfgGeminiKey');
    const saveBtn = document.getElementById('btnSaveTokens');
    const alertBox = document.getElementById('tokensSaveAlert');

    const tgToken = tgInput ? tgInput.value.trim() : '';
    const gemKey = gemInput ? gemInput.value.trim() : '';

    if (saveBtn) saveBtn.disabled = true;
    if (alertBox) {
        alertBox.style.display = 'block';
        alertBox.style.background = 'rgba(255,255,255,0.05)';
        alertBox.style.color = 'var(--text-secondary)';
        alertBox.innerHTML = '⏳ Salvando configurações e atualizando serviços...';
    }

    try {
        const res = await fetch('/api/system/tokens', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                telegram_bot_token: tgToken,
                gemini_api_key: gemKey
            })
        });
        const data = await res.json();
        
        if (alertBox) {
            if (data.success) {
                alertBox.style.background = 'rgba(16, 185, 129, 0.15)';
                alertBox.style.color = '#34d399';
                alertBox.style.border = '1px solid rgba(16, 185, 129, 0.3)';
                alertBox.innerHTML = '🎉 <b>Configurações Salvas com Sucesso!</b><br>' + (data.bot_status || 'Tokens aplicados.');
                
                // Recarrega status dos badges
                loadSystemTokens();
            } else {
                alertBox.style.background = 'rgba(239, 68, 68, 0.15)';
                alertBox.style.color = '#f87171';
                alertBox.style.border = '1px solid rgba(239, 68, 68, 0.3)';
                alertBox.innerHTML = '❌ ' + (data.message || 'Erro ao salvar configurações.');
            }
        }
    } catch (err) {
        if (alertBox) {
            alertBox.style.background = 'rgba(239, 68, 68, 0.15)';
            alertBox.style.color = '#f87171';
            alertBox.innerHTML = '❌ Erro de comunicação com o servidor ao salvar.';
        }
    } finally {
        if (saveBtn) saveBtn.disabled = false;
    }
}

/* ========================================================
   MODAL DE EXPORTAÇÃO E FILTROS DE RELATÓRIO (EXCEL / PDF)
   ======================================================== */
function openReportExportModal(format = 'excel') {
    const modal = document.getElementById('reportExportModal');
    if (!modal) return;

    // Set active format radio
    const formatRadio = document.querySelector(`input[name="repFormat"][value="${format}"]`);
    if (formatRadio) formatRadio.checked = true;

    // Default to current month preset
    setReportPeriod('current_month');

    modal.style.display = 'flex';
    modal.classList.add('show');
}

function closeReportExportModal() {
    const modal = document.getElementById('reportExportModal');
    if (modal) {
        modal.style.display = 'none';
        modal.classList.remove('show');
    }
}

function setReportPeriod(preset) {
    const now = new Date();
    const startInput = document.getElementById('repStartDate');
    const endInput = document.getElementById('repEndDate');

    // Update active style on preset buttons
    document.querySelectorAll('.period-preset-btn').forEach(b => {
        if (b.dataset.preset === preset) {
            b.classList.add('active');
            b.style.background = 'var(--primary)';
            b.style.color = '#fff';
            b.style.borderColor = 'var(--primary)';
        } else {
            b.classList.remove('active');
            b.style.background = 'rgba(255, 255, 255, 0.05)';
            b.style.color = 'var(--text-secondary)';
            b.style.borderColor = 'var(--border-subtle)';
        }
    });

    const formatDateStr = (d) => {
        const year = d.getFullYear();
        const month = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return `${year}-${month}-${day}`;
    };

    if (preset === 'current_month') {
        const start = new Date(now.getFullYear(), now.getMonth(), 1);
        const end = new Date(now.getFullYear(), now.getMonth() + 1, 0);
        if (startInput) startInput.value = formatDateStr(start);
        if (endInput) endInput.value = formatDateStr(end);
    } else if (preset === 'last_month') {
        const start = new Date(now.getFullYear(), now.getMonth() - 1, 1);
        const end = new Date(now.getFullYear(), now.getMonth(), 0);
        if (startInput) startInput.value = formatDateStr(start);
        if (endInput) endInput.value = formatDateStr(end);
    } else if (preset === 'last_3_months') {
        const start = new Date(now.getFullYear(), now.getMonth() - 2, 1);
        const end = new Date(now.getFullYear(), now.getMonth() + 1, 0);
        if (startInput) startInput.value = formatDateStr(start);
        if (endInput) endInput.value = formatDateStr(end);
    } else if (preset === 'current_year') {
        const start = new Date(now.getFullYear(), 0, 1);
        const end = new Date(now.getFullYear(), 11, 31);
        if (startInput) startInput.value = formatDateStr(start);
        if (endInput) endInput.value = formatDateStr(end);
    } else if (preset === 'custom') {
        if (startInput) startInput.focus();
    }
}

function submitCustomReport(e) {
    if (e) e.preventDefault();

    const format = document.querySelector('input[name="repFormat"]:checked')?.value || 'excel';
    const workspaceId = document.getElementById('repWorkspaceId')?.value || window.currentWorkspaceId || 1;
    const startDate = document.getElementById('repStartDate')?.value;
    const endDate = document.getElementById('repEndDate')?.value;
    const accountId = document.getElementById('repAccountId')?.value;
    const txType = document.getElementById('repTxType')?.value;
    const categoryId = document.getElementById('repCategoryId')?.value;
    const topExpensesLimit = document.getElementById('repTopExpenses')?.checked ? (document.getElementById('repTopLimit')?.value || '5') : '0';
    const includeComparison = document.getElementById('repComparison')?.checked ?? true;
    const includeMetrics = document.getElementById('repMetrics')?.checked ?? true;

    const params = new URLSearchParams();
    params.set('workspace_id', workspaceId);
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    if (accountId) params.set('account_id', accountId);
    if (txType) params.set('tx_type', txType);
    if (categoryId) params.set('category_id', categoryId);
    if (topExpensesLimit && topExpensesLimit !== '0') params.set('top_expenses_limit', topExpensesLimit);
    params.set('include_comparison', includeComparison ? 'true' : 'false');
    params.set('include_metrics', includeMetrics ? 'true' : 'false');

    const downloadUrl = `/export/${format}?${params.toString()}`;
    
    // Close modal and navigate/download
    closeReportExportModal();
    window.location.href = downloadUrl;
}

