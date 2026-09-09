let categoryChartInstance = null;
let cashflowChartInstance = null;

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initCharts();
    initRealtimeSync();
    loadMarketAnalyticsData();

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
    } else if (tabId === 'tab-items-analytics') {
        setTimeout(() => {
            loadMarketAnalyticsData();
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

/* ==========================================================================
   Gestão de Lançamentos, Upload de Comprovantes & Detalhamento de Itens
   ========================================================================== */

let currentTxItems = [];
let isIncludeItemsMode = true;
let currentViewingTxId = null;
let allItemsHistoryCache = [];

function openTransactionModal(defaultType = 'expense') {
    const modal = document.getElementById('transactionModal');
    if (!modal) return;

    // Reset Form
    const form = document.getElementById('transactionForm');
    if (form) form.reset();

    const typeSelect = document.getElementById('txType');
    if (typeSelect) typeSelect.value = defaultType;

    const dateInput = document.getElementById('txDate');
    if (dateInput) {
        const today = new Date().toISOString().split('T')[0];
        dateInput.value = today;
    }

    const receiptUrlInput = document.getElementById('txReceiptUrl');
    if (receiptUrlInput) receiptUrlInput.value = '';

    const previewPill = document.getElementById('receiptPreviewPill');
    if (previewPill) previewPill.style.display = 'none';

    const uploadLoader = document.getElementById('uploadLoader');
    if (uploadLoader) uploadLoader.classList.remove('active');

    // Reset items
    currentTxItems = [];
    setItemsMode(true);
    renderItemsTable();

    modal.style.display = 'flex';
    modal.classList.add('show', 'active');
    document.body.style.overflow = 'hidden';
}

function closeTransactionModal() {
    const modal = document.getElementById('transactionModal');
    if (!modal) return;
    modal.style.display = 'none';
    modal.classList.remove('show', 'active');
    document.body.style.overflow = '';
}


function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    const dropzone = document.getElementById('receiptDropzone');
    if (dropzone) dropzone.classList.add('dragover');
}

function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    const dropzone = document.getElementById('receiptDropzone');
    if (dropzone) dropzone.classList.remove('dragover');
}

function handleDropFile(e) {
    e.preventDefault();
    e.stopPropagation();
    const dropzone = document.getElementById('receiptDropzone');
    if (dropzone) dropzone.classList.remove('dragover');

    const files = e.dataTransfer?.files;
    if (files && files.length > 0) {
        uploadAndAnalyzeReceipt(files[0]);
    }
}

function handleFileSelected(e) {
    const files = e.target.files;
    if (files && files.length > 0) {
        uploadAndAnalyzeReceipt(files[0]);
    }
}

async function uploadAndAnalyzeReceipt(file) {
    if (!file) return;

    const dropzone = document.getElementById('receiptDropzone');
    const uploadLoader = document.getElementById('uploadLoader');
    const previewPill = document.getElementById('receiptPreviewPill');
    const fileNameSpan = document.getElementById('receiptFileName');
    const workspaceId = document.getElementById('txWorkspaceId')?.value || 1;
    const userId = document.getElementById('txUserId')?.value || 1;

    if (uploadLoader) uploadLoader.classList.add('active');

    const formData = new FormData();
    formData.append('file', file);
    formData.append('workspace_id', workspaceId);
    if (userId) formData.append('user_id', userId);

    try {
        const response = await fetch('/api/receipts/analyze', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (uploadLoader) uploadLoader.classList.remove('active');

        if (data.receipt_url) {
            const receiptUrlInput = document.getElementById('txReceiptUrl');
            if (receiptUrlInput) receiptUrlInput.value = data.receipt_url;
        }

        if (previewPill && fileNameSpan) {
            fileNameSpan.textContent = file.name;
            previewPill.style.display = 'inline-flex';
        }

        // Preenche campos da transação
        if (data.amount !== undefined && data.amount > 0) {
            const amountInput = document.getElementById('txAmount');
            if (amountInput) amountInput.value = parseFloat(data.amount).toFixed(2);
        }

        if (data.description) {
            const descInput = document.getElementById('txDescription');
            if (descInput) descInput.value = data.description;
        }

        if (data.type) {
            const typeSelect = document.getElementById('txType');
            if (typeSelect) typeSelect.value = data.type;
        }

        if (data.category_name) {
            const catInput = document.getElementById('txCategory');
            if (catInput) catInput.value = data.category_name;
        }

        if (data.date) {
            const dateInput = document.getElementById('txDate');
            if (dateInput) dateInput.value = data.date;
        }

        // Processa itens extraídos
        if (data.items && Array.isArray(data.items) && data.items.length > 0) {
            currentTxItems = data.items.map(it => ({
                name: it.name || '',
                quantity: parseFloat(it.quantity || 1),
                unit: it.unit || 'un',
                unit_price: parseFloat(it.unit_price || 0),
                total_price: parseFloat(it.total_price || 0),
                category: it.category || 'Geral'
            }));
            setItemsMode(true);
            renderItemsTable();
        } else {
            // Se nenhum item foi discriminado (ex: comprovante de Pix simples), mantém modo Total
            if (currentTxItems.length === 0) {
                setItemsMode(false);
            }
        }

    } catch (err) {
        if (uploadLoader) uploadLoader.classList.remove('active');
        console.error('Erro ao analisar comprovante:', err);
        alert('Não foi possível analisar o comprovante automaticamente. Preencha os dados manualmente.');
    }
}

function clearUploadedReceipt(e) {
    if (e) e.stopPropagation();
    const fileInput = document.getElementById('receiptFileInput');
    if (fileInput) fileInput.value = '';
    const receiptUrlInput = document.getElementById('txReceiptUrl');
    if (receiptUrlInput) receiptUrlInput.value = '';
    const previewPill = document.getElementById('receiptPreviewPill');
    if (previewPill) previewPill.style.display = 'none';
}

function setItemsMode(includeItems) {
    isIncludeItemsMode = includeItems;
    const btnItems = document.getElementById('btnModeItems');
    const btnTotal = document.getElementById('btnModeTotalOnly');
    const container = document.getElementById('itemsEditorContainer');

    if (btnItems && btnTotal) {
        if (includeItems) {
            btnItems.classList.add('active');
            btnTotal.classList.remove('active');
        } else {
            btnItems.classList.remove('active');
            btnTotal.classList.add('active');
        }
    }

    if (container) {
        container.style.display = includeItems ? 'block' : 'none';
    }

    if (includeItems && currentTxItems.length === 0) {
        addNewEmptyItemRow();
    }
}

function renderItemsTable() {
    const tbody = document.getElementById('txItemsTableBody');
    if (!tbody) return;

    if (currentTxItems.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 1.25rem;">
                    Nenhum produto adicionado. Clique em "+ Adicionar Produto Manualmente" ou carregue um comprovante/cupom fiscal.
                </td>
            </tr>
        `;
        updateItemsSummaryBar();
        return;
    }

    const categoriesOptions = [
        'Mercearia', 'Carnes & Aves', 'Hortifruti', 'Laticínios & Frios', 
        'Bebidas', 'Padaria & Sobremesas', 'Limpeza', 'Higiene & Beleza', 
        'Farmácia & Saúde', 'Pet Shop', 'Utilidades', 'Geral'
    ];

    tbody.innerHTML = currentTxItems.map((item, idx) => `
        <tr id="tx-item-row-${idx}">
            <td>
                <input type="text" value="${escapeHtml(item.name || '')}" placeholder="Ex: Arroz 5kg" oninput="updateItemField(${idx}, 'name', this.value)" required>
            </td>
            <td>
                <input type="number" step="0.01" min="0.01" value="${item.quantity}" oninput="updateItemField(${idx}, 'quantity', this.value)" style="text-align: center;">
            </td>
            <td>
                <select onchange="updateItemField(${idx}, 'unit', this.value)">
                    <option value="un" ${item.unit === 'un' ? 'selected' : ''}>un</option>
                    <option value="kg" ${item.unit === 'kg' ? 'selected' : ''}>kg</option>
                    <option value="g" ${item.unit === 'g' ? 'selected' : ''}>g</option>
                    <option value="l" ${item.unit === 'l' ? 'selected' : ''}>L</option>
                    <option value="pct" ${item.unit === 'pct' ? 'selected' : ''}>pct</option>
                    <option value="cx" ${item.unit === 'cx' ? 'selected' : ''}>cx</option>
                    <option value="dz" ${item.unit === 'dz' ? 'selected' : ''}>dz</option>
                </select>
            </td>
            <td>
                <input type="number" step="0.01" min="0" value="${item.unit_price ? parseFloat(item.unit_price).toFixed(2) : '0.00'}" oninput="updateItemField(${idx}, 'unit_price', this.value)" style="text-align: right;">
            </td>
            <td>
                <input type="number" step="0.01" min="0" value="${item.total_price ? parseFloat(item.total_price).toFixed(2) : '0.00'}" oninput="updateItemField(${idx}, 'total_price', this.value)" style="text-align: right; font-weight: 600;">
            </td>
            <td>
                <select onchange="updateItemField(${idx}, 'category', this.value)">
                    ${categoriesOptions.map(cat => `<option value="${cat}" ${item.category === cat ? 'selected' : ''}>${cat}</option>`).join('')}
                </select>
            </td>
            <td style="text-align: center;">
                <button type="button" class="btn-icon-danger" onclick="removeItemRow(${idx})" title="Remover item" style="padding: 0.2rem 0.4rem; font-size: 0.85rem;">✕</button>
            </td>
        </tr>
    `).join('');

    updateItemsSummaryBar();
}

function addNewEmptyItemRow() {
    currentTxItems.push({
        name: '',
        quantity: 1.0,
        unit: 'un',
        unit_price: 0.0,
        total_price: 0.0,
        category: 'Geral'
    });
    renderItemsTable();
}

function removeItemRow(idx) {
    if (idx >= 0 && idx < currentTxItems.length) {
        currentTxItems.splice(idx, 1);
        renderItemsTable();
    }
}

function detectSmartUnit(name) {
    if (!name) return null;
    const n = name.toLowerCase().trim();
    const kgWords = [
        'pao frances', 'pão francês', 'pao de sal', 'pão de sal', 'pao de queijo', 'pão de queijo', 'chipa',
        'queijo', 'mussarela', 'muçarela', 'presunto', 'mortadela', 'salame', 'peito de peru',
        'picanha', 'alcatra', 'maminha', 'contrafile', 'patinho', 'acem', 'acém', 'carne moida', 'carne moída',
        'costela', 'frango', 'peito de frango', 'linguica', 'linguiça', 'bacon', 'bisteca', 'peixe', 'salmao', 'tilapia',
        'tomate', 'banana', 'batata', 'cebola', 'alho', 'maca', 'maçã', 'laranja', 'cenoura', 'melancia',
        'abobrinha', 'berinjela', 'chuchu', 'beterraba', 'pimentao', 'uva', 'manga', 'limao', 'limão', 'mandioca'
    ];
    if (kgWords.some(w => n.includes(w))) return 'kg';
    if (['arroz', 'feijao', 'feijão', 'cafe', 'café', 'acucar', 'açúcar', 'farinha', 'macarrao', 'macarrão', 'biscoito'].some(w => n.includes(w))) return 'pct';
    if (['sabao em po', 'sabão em pó', 'bombom', 'remedio', 'remédio'].some(w => n.includes(w))) return 'cx';
    return null;
}

function updateItemField(idx, field, value) {
    if (!currentTxItems[idx]) return;

    if (field === 'name') {
        currentTxItems[idx].name = value;
        // Auto-detecta unidade típica (ex: Pão Francês -> KG)
        const smartUnit = detectSmartUnit(value);
        if (smartUnit && currentTxItems[idx].unit === 'un') {
            currentTxItems[idx].unit = smartUnit;
            const unitSelect = document.querySelector(`#tx-item-row-${idx} select[onchange*="unit"]`);
            if (unitSelect) unitSelect.value = smartUnit;
        }
    } else if (field === 'quantity') {
        const qty = parseFloat(value) || 0;
        currentTxItems[idx].quantity = qty;
        if (currentTxItems[idx].unit_price > 0) {
            currentTxItems[idx].total_price = parseFloat((qty * currentTxItems[idx].unit_price).toFixed(2));
            const rowTotalInput = document.querySelector(`#tx-item-row-${idx} input[oninput*="total_price"]`);
            if (rowTotalInput) rowTotalInput.value = currentTxItems[idx].total_price.toFixed(2);
        }
    } else if (field === 'unit_price') {
        const unitP = parseFloat(value) || 0;
        currentTxItems[idx].unit_price = unitP;
        currentTxItems[idx].total_price = parseFloat(((currentTxItems[idx].quantity || 1) * unitP).toFixed(2));
        const rowTotalInput = document.querySelector(`#tx-item-row-${idx} input[oninput*="total_price"]`);
        if (rowTotalInput) rowTotalInput.value = currentTxItems[idx].total_price.toFixed(2);
    } else if (field === 'total_price') {
        const totalP = parseFloat(value) || 0;
        currentTxItems[idx].total_price = totalP;
        const qty = currentTxItems[idx].quantity || 1;
        if (qty > 0) {
            currentTxItems[idx].unit_price = parseFloat((totalP / qty).toFixed(2));
            const rowUnitInput = document.querySelector(`#tx-item-row-${idx} input[oninput*="unit_price"]`);
            if (rowUnitInput) rowUnitInput.value = currentTxItems[idx].unit_price.toFixed(2);
        }
    } else {
        currentTxItems[idx][field] = value;
    }

    updateItemsSummaryBar();
}

function updateItemsSummaryBar() {
    const countSpan = document.getElementById('itemsCountLabel');
    const sumSpan = document.getElementById('itemsSumLabel');
    const amountInput = document.getElementById('txAmount');

    const totalSum = currentTxItems.reduce((acc, it) => acc + (parseFloat(it.total_price) || 0), 0);
    const validCount = currentTxItems.filter(it => it.name && it.name.trim()).length;

    if (countSpan) countSpan.textContent = validCount;
    if (sumSpan) {
        sumSpan.innerHTML = `Soma dos Itens: <b>${totalSum.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}</b> (${validCount} produtos)`;
    }

    // Se o valor total do formulário estiver vazio e tivermos soma de itens, sugere o valor
    if (amountInput && (!amountInput.value || parseFloat(amountInput.value) === 0) && totalSum > 0) {
        amountInput.value = totalSum.toFixed(2);
    }
}

async function saveTransactionForm(e) {
    if (e) e.preventDefault();

    const workspaceId = parseInt(document.getElementById('txWorkspaceId')?.value || 1);
    const userId = parseInt(document.getElementById('txUserId')?.value || 1);
    const type = document.getElementById('txType')?.value || 'expense';
    const amount = parseFloat(document.getElementById('txAmount')?.value || 0);
    const description = document.getElementById('txDescription')?.value?.trim();
    const categoryName = document.getElementById('txCategory')?.value?.trim() || 'Outros';
    const accountIdVal = document.getElementById('txAccount')?.value;
    const accountId = accountIdVal ? parseInt(accountIdVal) : null;
    const date = document.getElementById('txDate')?.value;
    const receiptUrl = document.getElementById('txReceiptUrl')?.value || null;

    if (!description) {
        alert('Por favor, informe a descrição ou nome do estabelecimento.');
        return;
    }

    if (isNaN(amount) || amount <= 0) {
        alert('Por favor, informe um valor válido maior que zero.');
        return;
    }

    // Filtra itens vazios
    const validItems = currentTxItems
        .filter(it => it.name && it.name.trim())
        .map(it => ({
            name: it.name.trim(),
            quantity: parseFloat(it.quantity) || 1.0,
            unit: it.unit || 'un',
            unit_price: parseFloat(it.unit_price) || 0.0,
            total_price: parseFloat(it.total_price) || 0.0,
            category: it.category || 'Geral'
        }));

    const payload = {
        workspace_id: workspaceId,
        user_id: userId,
        type: type,
        amount: amount,
        description: description,
        category_name: categoryName,
        payment_method: accountId ? 'Conta Bancária' : 'Outro',
        account_id: accountId,
        date: date,
        receipt_url: receiptUrl,
        include_items: isIncludeItemsMode,
        items: isIncludeItemsMode ? validItems : null
    };

    const saveBtn = document.getElementById('btnSaveTx');
    if (saveBtn) {
        saveBtn.disabled = true;
        saveBtn.textContent = 'Salvando...';
    }

    try {
        const res = await fetch('/api/transactions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (res.ok && data.success) {
            closeTransactionModal();
            window.location.reload();
        } else {
            alert('Erro ao salvar lançamento: ' + (data.detail || data.error || 'Erro desconhecido'));
        }
    } catch (err) {
        console.error(err);
        alert('Falha na comunicação com o servidor ao salvar o lançamento.');
    } finally {
        if (saveBtn) {
            saveBtn.disabled = false;
            saveBtn.textContent = '💾 Salvar Lançamento';
        }
    }
}

async function openTransactionItemsModal(transactionId) {
    currentViewingTxId = transactionId;
    const modal = document.getElementById('transactionItemsModal');
    if (!modal) return;

    const titleEl = document.getElementById('txItemsModalTitle');
    const subtitleEl = document.getElementById('txItemsModalSubtitle');
    const amountEl = document.getElementById('txItemsModalAmount');
    const catEl = document.getElementById('txItemsModalCategory');
    const dateEl = document.getElementById('txItemsModalDate');
    const tbody = document.getElementById('txItemsViewTableBody');
    const countEl = document.getElementById('txItemsViewCount');
    const totalEl = document.getElementById('txItemsViewTotal');

    if (tbody) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 2rem;">Carregando itens...</td></tr>`;
    }

    modal.style.display = 'flex';
    modal.classList.add('show', 'active');
    document.body.style.overflow = 'hidden';

    try {
        const res = await fetch(`/api/transactions/${transactionId}/items`);
        if (!res.ok) throw new Error('Falha ao carregar itens');
        const data = await res.json();

        if (titleEl) titleEl.textContent = `🛒 ${data.description}`;
        if (subtitleEl) subtitleEl.textContent = `Lançamento #${data.transaction_id} • ${data.date}`;
        if (amountEl) amountEl.textContent = Number(data.amount).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
        if (catEl) catEl.textContent = data.category;
        if (dateEl) dateEl.textContent = data.date;

        if (tbody) {
            if (!data.items || data.items.length === 0) {
                tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 2rem;">Nenhum item discriminado para este lançamento.</td></tr>`;
            } else {
                tbody.innerHTML = data.items.map(it => `
                    <tr>
                        <td style="font-weight: 600; color: #fff;">${escapeHtml(it.name)}</td>
                        <td><span class="category-tag">${escapeHtml(it.category || 'Geral')}</span></td>
                        <td style="text-align: center;">${it.quantity} ${it.unit}</td>
                        <td style="text-align: right; color: var(--text-secondary);">${Number(it.unit_price).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}</td>
                        <td style="text-align: right; font-weight: 700; color: #fff;">${Number(it.total_price).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}</td>
                    </tr>
                `).join('');
            }
        }

        const itemsSum = (data.items || []).reduce((acc, it) => acc + (it.total_price || 0), 0);
        if (countEl) countEl.textContent = `Total de produtos: ${(data.items || []).length}`;
        if (totalEl) totalEl.textContent = `Soma dos Itens: ${itemsSum.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}`;

    } catch (err) {
        console.error(err);
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: #fb7185; padding: 2rem;">Erro ao carregar itens deste lançamento.</td></tr>`;
        }
    }
}

function closeTransactionItemsModal() {
    const modal = document.getElementById('transactionItemsModal');
    if (!modal) return;
    modal.style.display = 'none';
    modal.classList.remove('show', 'active');
    document.body.style.overflow = '';
    currentViewingTxId = null;
}


async function confirmDeleteItemsKeepTotal() {
    if (!currentViewingTxId) return;

    if (!confirm('Deseja remover a lista de itens discriminados deste lançamento e manter apenas o valor total gasto no extrato?')) {
        return;
    }

    try {
        const res = await fetch(`/api/transactions/${currentViewingTxId}/items`, {
            method: 'DELETE'
        });

        if (res.ok) {
            closeTransactionItemsModal();
            window.location.reload();
        } else {
            alert('Não foi possível remover os itens.');
        }
    } catch (err) {
        console.error(err);
        alert('Erro ao conectar com o servidor.');
    }
}

/* ==========================================================================
   Central de Análise de Itens & Mercado
   ========================================================================== */

// ==========================================================================
// Módulo de Inteligência de Mercado, Rankings & Comparador de Preços
// ==========================================================================
let currentItemRankingSort = 'spent';
let allPriceComparisonsCache = [];
let priceLookupTimeout = null;

async function loadMarketAnalyticsData() {
    const workspaceId = window.currentWorkspaceId || 1;
    const urlParams = new URLSearchParams(window.location.search);
    const year = window.selectedYear || urlParams.get('year');
    const month = window.selectedMonth || urlParams.get('month');

    const params = new URLSearchParams();
    params.set('workspace_id', workspaceId);
    if (year) params.set('year', year);
    if (month) params.set('month', month);

    try {
        // 1. Carrega Estatísticas Básicas e Categorias
        const [resAnalytics, resRanking, resComparisons] = await Promise.all([
            fetch(`/api/analytics/items?${params.toString()}`),
            fetch(`/api/market/ranking?workspace_id=${workspaceId}&sort_by=${currentItemRankingSort}${year ? '&year='+year : ''}${month ? '&month='+month : ''}`),
            fetch(`/api/market/compare-prices?workspace_id=${workspaceId}`)
        ]);

        if (resAnalytics.ok) {
            const data = await resAnalytics.json();
            const totalItemsEl = document.getElementById('analyticsTotalItems');
            const totalSpentEl = document.getElementById('analyticsTotalSpent');
            const totalCategoriesEl = document.getElementById('analyticsTotalCategories');

            if (totalItemsEl) totalItemsEl.textContent = data.total_items_count || 0;
            if (totalSpentEl) totalSpentEl.textContent = Number(data.total_spent_on_items || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
            if (totalCategoriesEl) totalCategoriesEl.textContent = (data.categories || []).length;

            // Categorias
            const topCatContainer = document.getElementById('topCategoriesList');
            if (topCatContainer) {
                const catList = data.categories || [];
                if (catList.length === 0) {
                    topCatContainer.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 1.5rem;">Nenhuma categoria registrada no período.</div>`;
                } else {
                    const maxCatSpent = catList[0]?.total_spent || 1;
                    topCatContainer.innerHTML = catList.map((cat, idx) => {
                        const pct = Math.min(100, Math.round((cat.total_spent / maxCatSpent) * 100));
                        const itemsArr = cat.items_list || [];
                        const itemsListHtml = itemsArr.length > 0 ? `
                            <div class="tooltip-items-list">
                                <div style="font-weight: 700; color: #94a3b8; font-size: 0.72rem; margin-bottom: 0.2rem;">🛍️ Itens da Categoria:</div>
                                ${itemsArr.slice(0, 6).map(it => `
                                    <div class="tooltip-item-pill">
                                        <span>${escapeHtml(it.name)} (${it.total_quantity} ${it.unit || ''})</span>
                                        <span>${Number(it.total_spent).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}</span>
                                    </div>
                                `).join('')}
                                ${itemsArr.length > 6 ? `<div style="text-align: center; font-size: 0.7rem; color: #94a3b8;">+ ${itemsArr.length - 6} outros itens</div>` : ''}
                            </div>
                        ` : '';

                        return `
                            <div class="ranking-item">
                                <div class="ranking-header-row">
                                    <div class="ranking-title-group">
                                        <div class="ranking-rank" style="background: rgba(16, 185, 129, 0.2); color: #34d399;">🏷️</div>
                                        <div class="ranking-name" title="${escapeHtml(cat.category)}">${escapeHtml(cat.category)}</div>
                                    </div>
                                    <div class="ranking-amount">${Number(cat.total_spent).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}</div>
                                </div>
                                <div class="ranking-bar-wrap">
                                    <div class="ranking-bar-fill" style="width: ${pct}%; background: linear-gradient(90deg, #10b981, #06b6d4);"></div>
                                </div>
                                <div class="ranking-sub-row">
                                    <span>${cat.items_count} produtos no período</span>
                                </div>
                                <div class="ranking-tooltip">
                                    <div class="tooltip-header">
                                        <span>🏷️</span>
                                        <div class="tooltip-title">${escapeHtml(cat.category)}</div>
                                    </div>
                                    <div class="tooltip-body">
                                        <div class="tooltip-row"><span>Total Gasto:</span> <b>${Number(cat.total_spent).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}</b></div>
                                        <div class="tooltip-row"><span>Produtos Distintos:</span> <b>${cat.items_count} itens</b></div>
                                        ${itemsListHtml}
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('');
                }
            }

            // Histórico de Itens
            allItemsHistoryCache = data.recent_items || [];
            renderItemsHistoryTable(allItemsHistoryCache);
        }

        // 2. Renderiza Ranking de Produtos e Mercados
        if (resRanking.ok) {
            const rankingData = await resRanking.json();
            renderTopConsumedItems(rankingData.top_items || []);
            renderSupermarketRanking(rankingData.top_stores || []);

            const totalStoresEl = document.getElementById('analyticsTotalStores');
            if (totalStoresEl) totalStoresEl.textContent = (rankingData.top_stores || []).length;
        }

        // 3. Renderiza Comparador de Preços entre Supermercados
        if (resComparisons.ok) {
            const compData = await resComparisons.json();
            allPriceComparisonsCache = compData.comparisons || [];
            renderPriceComparisonTable(allPriceComparisonsCache);
        }

    } catch (err) {
        console.error('Erro ao carregar inteligência de mercado:', err);
    }
}

function switchItemRankingSort(sortBy) {
    currentItemRankingSort = sortBy;
    const btnSpent = document.getElementById('btnSortSpent');
    const btnQty = document.getElementById('btnSortQty');
    if (btnSpent && btnQty) {
        if (sortBy === 'spent') {
            btnSpent.classList.add('active');
            btnQty.classList.remove('active');
        } else {
            btnQty.classList.add('active');
            btnSpent.classList.remove('active');
        }
    }
    loadMarketAnalyticsData();
}

function renderTopConsumedItems(items) {
    const container = document.getElementById('topSpentList');
    if (!container) return;

    if (!items || items.length === 0) {
        container.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 1.5rem;">Nenhum produto cadastrado no período.</div>`;
        return;
    }

    const isSpent = currentItemRankingSort === 'spent';
    const maxVal = isSpent ? (items[0]?.total_spent || 1) : (items[0]?.total_quantity || 1);

    container.innerHTML = items.slice(0, 10).map((item, idx) => {
        const val = isSpent ? item.total_spent : item.total_quantity;
        const pct = Math.min(100, Math.round((val / maxVal) * 100));
        const rankClass = idx === 0 ? 'top-1' : (idx === 1 ? 'top-2' : (idx === 2 ? 'top-3' : ''));
        const storesText = item.stores_count > 1 ? `🏪 ${item.stores_count} mercados` : `🏪 ${escapeHtml(item.last_store)}`;
        const storesListStr = (item.stores_list || []).join(', ') || item.last_store;

        return `
            <div class="ranking-item">
                <div class="ranking-header-row">
                    <div class="ranking-title-group">
                        <div class="ranking-rank ${rankClass}">${idx + 1}</div>
                        <div class="ranking-name" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</div>
                    </div>
                    <div class="ranking-amount">${Number(item.total_spent).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}</div>
                </div>
                <div class="ranking-bar-wrap">
                    <div class="ranking-bar-fill" style="width: ${pct}%;"></div>
                </div>
                <div class="ranking-sub-row">
                    <span>${item.total_quantity} ${item.unit} • Médio ${Number(item.avg_unit_price).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}</span>
                    <span style="color: #a5b4fc; font-weight: 500;">${storesText}</span>
                </div>
                <div class="ranking-tooltip">
                    <div class="tooltip-header">
                        <span>🛒</span>
                        <div class="tooltip-title">${escapeHtml(item.name)}</div>
                    </div>
                    <div class="tooltip-badge-cat">🏷️ ${escapeHtml(item.category || 'Geral')}</div>
                    <div class="tooltip-body">
                        <div class="tooltip-row"><span>Total Gasto:</span> <b>${Number(item.total_spent).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}</b></div>
                        <div class="tooltip-row"><span>Volume Total:</span> <b>${item.total_quantity} ${item.unit}</b></div>
                        <div class="tooltip-row"><span>Preço Médio:</span> <b>${Number(item.avg_unit_price).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })} / ${item.unit}</b></div>
                        <div class="tooltip-row"><span>Última Compra:</span> <b>${Number(item.last_unit_price).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })} (${item.last_purchase_date || 'Recente'})</b></div>
                        <div class="tooltip-row"><span>Estabelecimento:</span> <b>${escapeHtml(storesListStr)}</b></div>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function renderSupermarketRanking(stores) {
    const container = document.getElementById('topStoresList');
    if (!container) return;

    if (!stores || stores.length === 0) {
        container.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 1.5rem;">Nenhum supermercado registrado ainda.</div>`;
        return;
    }

    const maxSpent = stores[0]?.total_spent || 1;

    container.innerHTML = stores.map((s, idx) => {
        const pct = Math.min(100, Math.round((s.total_spent / maxSpent) * 100));
        const rankClass = idx === 0 ? 'top-1' : (idx === 1 ? 'top-2' : (idx === 2 ? 'top-3' : ''));
        const itemsArr = s.items_list || [];
        const itemsListHtml = itemsArr.length > 0 ? `
            <div class="tooltip-items-list">
                <div style="font-weight: 700; color: #94a3b8; font-size: 0.72rem; margin-bottom: 0.2rem;">🛍️ Itens Comprados no Local:</div>
                ${itemsArr.slice(0, 6).map(it => `
                    <div class="tooltip-item-pill">
                        <span>${escapeHtml(it.name)} (${it.quantity} ${it.unit || ''})</span>
                        <span>${Number(it.total_spent).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}</span>
                    </div>
                `).join('')}
                ${itemsArr.length > 6 ? `<div style="text-align: center; font-size: 0.7rem; color: #94a3b8;">+ ${itemsArr.length - 6} outros itens</div>` : ''}
            </div>
        ` : '';

        return `
            <div class="ranking-item">
                <div class="ranking-header-row">
                    <div class="ranking-title-group">
                        <div class="ranking-rank ${rankClass}">${idx + 1}</div>
                        <div class="ranking-name" title="${escapeHtml(s.store_name)}">${escapeHtml(s.store_name)}</div>
                    </div>
                    <div class="ranking-amount">${Number(s.total_spent).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}</div>
                </div>
                <div class="ranking-bar-wrap">
                    <div class="ranking-bar-fill" style="width: ${pct}%; background: linear-gradient(90deg, #6366f1, #ec4899);"></div>
                </div>
                <div class="ranking-sub-row">
                    <span>${s.transaction_count} compras • Ticket Médio ${Number(s.avg_ticket).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}</span>
                    <span style="color: #cbd5e1;">${s.last_visit ? 'Visita: ' + s.last_visit : ''}</span>
                </div>
                <div class="ranking-tooltip">
                    <div class="tooltip-header">
                        <span>🏪</span>
                        <div class="tooltip-title">${escapeHtml(s.store_name)}</div>
                    </div>
                    <div class="tooltip-body">
                        <div class="tooltip-row"><span>Total Gasto:</span> <b>${Number(s.total_spent).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}</b></div>
                        <div class="tooltip-row"><span>Compras Realizadas:</span> <b>${s.transaction_count} (Médio ${Number(s.avg_ticket).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })})</b></div>
                        <div class="tooltip-row"><span>Última Visita:</span> <b>${s.last_visit || 'N/A'}</b></div>
                        ${itemsListHtml}
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function renderPriceComparisonTable(comparisons) {
    const tbody = document.getElementById('priceComparisonTableBody');
    if (!tbody) return;

    if (!comparisons || comparisons.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" style="text-align: center; color: var(--text-muted); padding: 2rem;">
                    Nenhum produto cadastrado para comparação de preços. Envie cupons de diferentes mercados para analisar!
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = comparisons.map(prod => {
        const cheapest = prod.cheapest_store;
        const mostExp = prod.most_expensive_store;
        const hasDiff = prod.has_multi_store_comparison && mostExp;

        let diffBadge = '';
        if (hasDiff && prod.diff_pct > 0) {
            diffBadge = `
                <div style="text-align: center;">
                    <span class="badge" style="background: rgba(244, 63, 94, 0.15); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.35); font-size: 0.76rem; font-weight: 700; padding: 0.2rem 0.5rem;">
                        +${prod.diff_pct}% (+${Number(prod.price_diff).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })})
                    </span>
                    <small style="display: block; color: #34d399; font-size: 0.72rem; margin-top: 0.15rem;">
                        Economize no ${escapeHtml(cheapest.store_name)}
                    </small>
                </div>
            `;
        } else {
            diffBadge = `<span style="color: var(--text-muted); font-size: 0.78rem;">Preço Único Registrado</span>`;
        }

        const allStoresBadges = (prod.all_stores || []).map(st => {
            const isCheap = st.store_name === cheapest?.store_name;
            const bg = isCheap ? 'rgba(16, 185, 129, 0.12)' : 'rgba(255, 255, 255, 0.05)';
            const border = isCheap ? 'rgba(16, 185, 129, 0.35)' : 'rgba(255, 255, 255, 0.1)';
            const txt = isCheap ? '#34d399' : 'var(--text-secondary)';
            return `
                <span style="display: inline-flex; align-items: center; gap: 0.3rem; background: ${bg}; border: 1px solid ${border}; color: ${txt}; padding: 0.2rem 0.45rem; border-radius: 4px; font-size: 0.75rem; margin: 0.15rem 0.2rem 0.15rem 0;">
                    <b>${escapeHtml(st.store_name)}:</b> ${Number(st.latest_price).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}/${st.unit}
                </span>
            `;
        }).join('');

        return `
            <tr>
                <td style="font-weight: 700; color: #fff;">
                    ${escapeHtml(prod.product_name)}
                </td>
                <td><span class="category-tag">${escapeHtml(prod.category || 'Geral')}</span></td>
                <td>
                    <div style="display: flex; flex-direction: column;">
                        <strong style="color: #34d399; font-size: 0.95rem;">
                            ${Number(cheapest.price).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })} <small style="font-weight: normal; color: #a5b4fc;">/${cheapest.unit}</small>
                        </strong>
                        <small style="color: var(--text-secondary); font-size: 0.76rem;">
                            🏪 ${escapeHtml(cheapest.store_name)} (${cheapest.date})
                        </small>
                    </div>
                </td>
                <td>
                    ${mostExp ? `
                        <div style="display: flex; flex-direction: column;">
                            <strong style="color: #fb7185; font-size: 0.95rem;">
                                ${Number(mostExp.price).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })} <small style="font-weight: normal; color: #a5b4fc;">/${mostExp.unit}</small>
                            </strong>
                            <small style="color: var(--text-secondary); font-size: 0.76rem;">
                                🏪 ${escapeHtml(mostExp.store_name)} (${mostExp.date})
                            </small>
                        </div>
                    ` : `<span style="color: var(--text-muted); font-size: 0.8rem;">-</span>`}
                </td>
                <td style="text-align: center;">${diffBadge}</td>
                <td style="max-width: 250px;">
                    <div style="display: flex; flex-wrap: wrap;">${allStoresBadges}</div>
                </td>
            </tr>
        `;
    }).join('');
}

function filterPriceComparisonTable(query) {
    if (!query || !query.trim()) {
        renderPriceComparisonTable(allPriceComparisonsCache);
        return;
    }
    const q = query.toLowerCase().trim();
    const filtered = allPriceComparisonsCache.filter(p => 
        (p.product_name && p.product_name.toLowerCase().includes(q)) ||
        (p.category && p.category.toLowerCase().includes(q)) ||
        (p.all_stores && p.all_stores.some(st => st.store_name && st.store_name.toLowerCase().includes(q)))
    );
    renderPriceComparisonTable(filtered);
}

function renderItemsHistoryTable(items) {
    const tbody = document.getElementById('itemsHistoryTableBody');
    if (!tbody) return;

    if (!items || items.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" style="text-align: center; color: var(--text-muted); padding: 2rem;">
                    Nenhum item encontrado no histórico deste período.
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = items.map(it => `
        <tr>
            <td>${it.transaction_date}</td>
            <td style="font-weight: 500;">
                <a href="javascript:void(0)" onclick="openTransactionItemsModal(${it.transaction_id})" style="color: #818cf8; text-decoration: none;">
                    ${escapeHtml(it.transaction_desc || 'Compra')}
                </a>
            </td>
            <td style="font-weight: 600; color: #fff;">${escapeHtml(it.name)}</td>
            <td><span class="category-tag">${escapeHtml(it.category || 'Geral')}</span></td>
            <td style="text-align: center;">${it.quantity} ${it.unit}</td>
            <td style="text-align: right; color: var(--text-secondary);">${Number(it.unit_price).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}</td>
            <td style="text-align: right; font-weight: 700; color: #fff;">${Number(it.total_price).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}</td>
        </tr>
    `).join('');
}

function filterItemsHistoryTable(query) {
    if (!query || !query.trim()) {
        renderItemsHistoryTable(allItemsHistoryCache);
        return;
    }
    const q = query.toLowerCase().trim();
    const filtered = allItemsHistoryCache.filter(it => 
        (it.name && it.name.toLowerCase().includes(q)) ||
        (it.category && it.category.toLowerCase().includes(q)) ||
        (it.transaction_desc && it.transaction_desc.toLowerCase().includes(q))
    );
    renderItemsHistoryTable(filtered);
}

// ==========================================================================
// Lista de Mercado com Auto-Estimativa de Preço da Última Compra
// ==========================================================================
function debounceLookupPrice(itemName) {
    if (priceLookupTimeout) clearTimeout(priceLookupTimeout);
    const hintEl = document.getElementById('shopLastPriceHint');
    if (!itemName || itemName.trim().length < 2) {
        if (hintEl) hintEl.style.display = 'none';
        return;
    }
    priceLookupTimeout = setTimeout(() => lookupLastPrice(itemName), 300);
}

async function lookupLastPrice(itemName) {
    const hintEl = document.getElementById('shopLastPriceHint');
    const priceInput = document.getElementById('shopItemPrice');
    const unitSelect = document.getElementById('shopItemUnit');
    const wsId = window.currentWorkspaceId || 1;

    try {
        const res = await fetch(`/api/market/last-price?workspace_id=${wsId}&item_name=${encodeURIComponent(itemName)}`);
        if (!res.ok) return;
        const data = await res.json();

        if (data.unit && unitSelect) {
            unitSelect.value = data.unit;
        }

        if (data.found && hintEl) {
            hintEl.style.display = 'block';
            let tipHtml = data.unit_tip ? `<span style="color:#f59e0b; font-weight:600;">${escapeHtml(data.unit_tip)}</span><br>` : '';
            hintEl.innerHTML = `${tipHtml}🏷️ <b>Última Compra:</b> ${Number(data.estimated_unit_price).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}/${data.unit} no <i>${escapeHtml(data.last_store)}</i> (${data.last_date})`;
            
            if (priceInput && (!priceInput.value || Number(priceInput.value) === 0)) {
                priceInput.value = data.estimated_unit_price;
            }
        } else if (data.unit_tip && hintEl) {
            hintEl.style.display = 'block';
            hintEl.innerHTML = `<span style="color:#f59e0b; font-weight:600;">${escapeHtml(data.unit_tip)}</span>`;
        } else if (hintEl) {
            hintEl.style.display = 'none';
        }
    } catch (e) {
        console.error('Erro ao consultar último preço:', e);
    }
}

async function handleAddShoppingItem(event) {
    event.preventDefault();
    const wsId = window.currentWorkspaceId || 1;
    const nameInput = document.getElementById('shopItemName');
    const qtyInput = document.getElementById('shopItemQty');
    const unitInput = document.getElementById('shopItemUnit');
    const priceInput = document.getElementById('shopItemPrice');
    const hintEl = document.getElementById('shopLastPriceHint');

    if (!nameInput || !nameInput.value.trim()) return;

    const payload = {
        workspace_id: wsId,
        name: nameInput.value.trim(),
        quantity: parseFloat(qtyInput.value) || 1.0,
        unit: unitInput.value || 'un',
        estimated_price: parseFloat(priceInput.value) || 0.0
    };

    try {
        const res = await fetch('/api/shopping/items', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!res.ok) throw new Error('Falha ao adicionar item');
        const data = await res.json();

        // Limpa formulário
        nameInput.value = '';
        qtyInput.value = '1';
        priceInput.value = '';
        if (hintEl) hintEl.style.display = 'none';

        // Atualiza total estimado no cabeçalho
        const totalEstEl = document.getElementById('shoppingTotalEstimated');
        if (totalEstEl && data.list_total_estimated !== undefined) {
            totalEstEl.textContent = Number(data.list_total_estimated).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
        }

        // Recarrega lista de compras
        window.location.reload();

    } catch (err) {
        console.error(err);
        alert('Não foi possível adicionar o produto à lista.');
    }
}

async function deleteShoppingItem(itemId, name) {
    if (!confirm(`Deseja remover "${name}" da lista de compras?`)) return;

    try {
        const res = await fetch(`/api/shopping/items/${itemId}`, { method: 'DELETE' });
        if (res.ok) {
            const row = document.getElementById(`shopItemRow_${itemId}`);
            if (row) row.remove();
            window.location.reload();
        } else {
            alert('Não foi possível remover o item.');
        }
    } catch (e) {
        console.error(e);
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// Global window assignments
window.openTransactionItemsModal = openTransactionItemsModal;
window.closeTransactionItemsModal = closeTransactionItemsModal;
window.openTransactionModal = openTransactionModal;
window.closeTransactionModal = closeTransactionModal;
window.setItemsMode = setItemsMode;
window.addNewEmptyItemRow = addNewEmptyItemRow;
window.removeItemRow = removeItemRow;
window.updateItemField = updateItemField;
window.confirmDeleteItemsKeepTotal = confirmDeleteItemsKeepTotal;
window.filterItemsHistoryTable = filterItemsHistoryTable;
window.handleDragOver = handleDragOver;
window.handleDragLeave = handleDragLeave;
window.handleDropFile = handleDropFile;
window.handleFileSelected = handleFileSelected;
window.clearUploadedReceipt = clearUploadedReceipt;
window.saveTransactionForm = saveTransactionForm;
window.loadItemsAnalytics = loadMarketAnalyticsData;
window.loadMarketAnalyticsData = loadMarketAnalyticsData;
window.switchItemRankingSort = switchItemRankingSort;
window.filterPriceComparisonTable = filterPriceComparisonTable;
window.debounceLookupPrice = debounceLookupPrice;
window.lookupLastPrice = lookupLastPrice;
window.handleAddShoppingItem = handleAddShoppingItem;
window.deleteShoppingItem = deleteShoppingItem;




