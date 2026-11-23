/**
 * OrderFlow - Frontend Application Logic
 * Handles real-time UI interactions, REST API integration, modals, and dynamic calculations.
 */

// Global State
let currentTab = 'dashboard';
let cachedCustomers = [];
let cachedItems = [];
let orderCart = []; // [{ item_code, name, price, quantity, maxStock, subtotal }]

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  initIcons();
  checkDbStatus();
  loadDashboard();
  loadCustomers();
  loadItems();
  loadOrders();
});

function initIcons() {
  if (window.lucide) {
    window.lucide.createIcons();
  }
}

// -------------------------------------------------------------
// Toast Notifications
// -------------------------------------------------------------
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast-item toast-${type}`;
  
  let iconName = 'info';
  if (type === 'success') iconName = 'check-circle';
  if (type === 'error') iconName = 'alert-circle';
  if (type === 'warning') iconName = 'alert-triangle';

  toast.innerHTML = `
    <div class="flex items-center gap-2">
      <i data-lucide="${iconName}" class="w-4 h-4"></i>
      <span>${escapeHtml(message)}</span>
    </div>
    <button onclick="this.parentElement.remove()" class="text-slate-400 hover:text-slate-600 ml-3">&times;</button>
  `;
  container.appendChild(toast);
  initIcons();

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    setTimeout(() => toast.remove(), 250);
  }, 4000);
}

// -------------------------------------------------------------
// Tab Switching
// -------------------------------------------------------------
function switchTab(tabName) {
  currentTab = tabName;
  document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(el => {
    el.classList.remove('border-brand-600', 'text-brand-600', 'font-semibold');
    el.classList.add('border-transparent', 'text-slate-500', 'font-medium');
  });

  const activePane = document.getElementById(`tab-${tabName}`);
  const activeNav = document.getElementById(`nav-${tabName}`);

  if (activePane) activePane.classList.add('active');
  if (activeNav) {
    activeNav.classList.remove('border-transparent', 'text-slate-500', 'font-medium');
    activeNav.classList.add('border-brand-600', 'text-brand-600', 'font-semibold');
  }

  // Refresh tab content
  if (tabName === 'dashboard') loadDashboard();
  else if (tabName === 'customers') loadCustomers();
  else if (tabName === 'items') loadItems();
  else if (tabName === 'orders') loadOrders();

  initIcons();
}

// -------------------------------------------------------------
// Modal Management
// -------------------------------------------------------------
function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.add('active');
    initIcons();
  }
  // Populate specific modal dependencies
  if (modalId === 'create-order-modal') {
    initCreateOrderModal();
  }
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.remove('active');
  }
}

// Close modals when clicking backdrop
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.classList.remove('active');
  }
});

// -------------------------------------------------------------
// Database Status & Connection
// -------------------------------------------------------------
async function checkDbStatus() {
  const dot = document.getElementById('db-indicator-dot');
  const text = document.getElementById('db-status-text');
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    const isConnected = data.connected_to_mysql || data.connected_to_mongodb;
    if (isConnected) {
      dot.className = 'w-2.5 h-2.5 rounded-full bg-emerald-500';
      text.innerText = data.connected_to_mysql ? 'MySQL Active' : 'DB Active';
      text.parentElement.title = `Connected: ${data.database_name} (${data.engine})`;
    } else {
      dot.className = 'w-2.5 h-2.5 rounded-full bg-amber-500';
      text.innerText = 'Local Store (DB Offline)';
      text.parentElement.title = data.message + ' (Click to retry)';
    }
  } catch (err) {
    dot.className = 'w-2.5 h-2.5 rounded-full bg-rose-500';
    text.innerText = 'DB Offline';
  }
}

async function reconnectDb() {
  const dot = document.getElementById('db-indicator-dot');
  const text = document.getElementById('db-status-text');
  if (dot) dot.className = 'w-2.5 h-2.5 rounded-full bg-amber-500 animate-ping';
  if (text) text.innerText = 'Connecting...';
  try {
    const res = await fetch('/api/db/reconnect', { method: 'POST' });
    const data = await res.json();
    const isConnected = data.connected_to_mysql || data.connected_to_mongodb;
    if (isConnected) {
      if (dot) dot.className = 'w-2.5 h-2.5 rounded-full bg-emerald-500';
      if (text) {
        text.innerText = data.connected_to_mysql ? 'MySQL Active' : 'DB Active';
        text.parentElement.title = `Connected: ${data.database_name} (${data.engine})`;
      }
      showToast(`Successfully connected to ${data.engine}!`, 'success');
      loadDashboard();
      loadCustomers();
      loadItems();
      loadOrders();
    } else {
      if (dot) dot.className = 'w-2.5 h-2.5 rounded-full bg-amber-500';
      if (text) {
        text.innerText = 'Local Store (DB Offline)';
        text.parentElement.title = data.message + ' (Click to retry)';
      }
      showToast(data.message || 'Database not reachable. Running in Local Store mode.', 'warning');
    }
  } catch (err) {
    if (dot) dot.className = 'w-2.5 h-2.5 rounded-full bg-rose-500';
    if (text) text.innerText = 'DB Offline';
    showToast('Failed to reach database endpoint', 'error');
  }
}

// -------------------------------------------------------------
// Dashboard Operations
// -------------------------------------------------------------
async function loadDashboard() {
  try {
    const res = await fetch('/api/dashboard');
    const data = await res.json();

    document.getElementById('dash-total-revenue').innerText = `$${formatMoney(data.total_revenue)}`;
    document.getElementById('dash-total-orders').innerText = data.total_orders;
    document.getElementById('dash-order-status-split').innerText = `${data.pending_orders} in progress &bull; ${data.completed_orders} completed`;
    document.getElementById('dash-total-customers').innerText = data.total_customers;
    document.getElementById('dash-total-items').innerText = data.total_items;
    
    const lowCount = data.low_stock_items ? data.low_stock_items.length : 0;
    const lowCountEl = document.getElementById('dash-low-stock-count');
    lowCountEl.innerText = `${lowCount} Low Stock alert(s)`;
    if (lowCount > 0) {
      lowCountEl.className = 'inline-flex items-center text-xs text-rose-600 font-bold mt-1';
    }

    // Render Recent Orders
    const tbody = document.getElementById('dash-recent-orders-body');
    if (data.recent_orders && data.recent_orders.length > 0) {
      tbody.innerHTML = data.recent_orders.map(o => `
        <tr class="hover:bg-slate-50 transition">
          <td class="px-5 py-3 font-semibold text-brand-600 font-mono">${escapeHtml(o.order_number)}</td>
          <td class="px-4 py-3 font-medium text-slate-800">${escapeHtml(o.customer_name)}</td>
          <td class="px-4 py-3 text-slate-500">${o.item_count || o.items?.length || 0} pcs</td>
          <td class="px-4 py-3 font-bold text-slate-900">$${formatMoney(o.total)}</td>
          <td class="px-4 py-3">${getStatusBadge(o.status)}</td>
          <td class="px-4 py-3 text-right">
            <button onclick="viewOrderInvoice('${o.order_number}')" class="text-xs font-semibold text-brand-600 hover:text-brand-800">
              Invoice
            </button>
          </td>
        </tr>
      `).join('');
    } else {
      tbody.innerHTML = `<tr><td colspan="6" class="px-5 py-6 text-center text-slate-400">No orders created yet. Click '+ New Order' to begin.</td></tr>`;
    }

    // Render Low Stock List
    const lowList = document.getElementById('dash-low-stock-list');
    if (data.low_stock_items && data.low_stock_items.length > 0) {
      lowList.innerHTML = data.low_stock_items.map(it => `
        <div class="py-2.5 flex items-center justify-between">
          <div>
            <p class="font-semibold text-slate-800 text-xs">${escapeHtml(it.name)}</p>
            <p class="text-[11px] text-slate-400 font-mono">${escapeHtml(it.item_code)}</p>
          </div>
          <div class="text-right">
            <span class="badge ${it.stock <= 0 ? 'badge-danger' : 'badge-warning'}">
              ${it.stock} remaining
            </span>
          </div>
        </div>
      `).join('');
    } else {
      lowList.innerHTML = `<p class="text-xs text-slate-400 text-center py-4">All products are healthy in inventory!</p>`;
    }

    initIcons();
  } catch (err) {
    console.error('Error loading dashboard:', err);
  }
}

// -------------------------------------------------------------
// Customers Operations
// -------------------------------------------------------------
async function loadCustomers() {
  const searchInput = document.getElementById('customers-search');
  const query = searchInput ? searchInput.value.trim() : '';
  const tbody = document.getElementById('customers-table-body');

  try {
    const res = await fetch(`/api/customers?search=${encodeURIComponent(query)}`);
    const customers = await res.json();
    cachedCustomers = customers;

    if (customers.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="px-5 py-8 text-center text-slate-400">No customers found matching "${escapeHtml(query)}".</td></tr>`;
      return;
    }

    tbody.innerHTML = customers.map(c => `
      <tr class="hover:bg-slate-50 transition">
        <td class="px-5 py-3 font-mono font-semibold text-xs text-brand-600">${escapeHtml(c.customer_id)}</td>
        <td class="px-5 py-3">
          <p class="font-semibold text-slate-900">${escapeHtml(c.name)}</p>
          <p class="text-xs text-slate-500">${escapeHtml(c.email)}</p>
        </td>
        <td class="px-5 py-3 text-xs text-slate-600">${escapeHtml(c.phone || '-')}</td>
        <td class="px-5 py-3 text-xs text-slate-600">${escapeHtml(c.city || c.address || '-')}</td>
        <td class="px-4 py-3 text-center">
          <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-brand-50 text-brand-700">
            ${c.order_count || 0}
          </span>
        </td>
        <td class="px-5 py-3 text-right font-bold text-slate-900">$${formatMoney(c.total_spent || 0)}</td>
        <td class="px-5 py-3 text-right whitespace-nowrap">
          <div class="inline-flex items-center gap-1.5">
            <button onclick="openCustomerProfile('${c.customer_id}')" title="View Profile & Orders" 
                    class="p-1.5 text-slate-500 hover:text-brand-600 hover:bg-slate-100 rounded-md transition">
              <i data-lucide="eye" class="w-4 h-4"></i>
            </button>
            <button onclick="openEditCustomer('${c.customer_id}')" title="Edit Customer" 
                    class="p-1.5 text-slate-500 hover:text-amber-600 hover:bg-slate-100 rounded-md transition">
              <i data-lucide="edit-2" class="w-4 h-4"></i>
            </button>
            <button onclick="confirmDeleteCustomer('${c.customer_id}')" title="Delete Customer" 
                    class="p-1.5 text-slate-500 hover:text-rose-600 hover:bg-slate-100 rounded-md transition">
              <i data-lucide="trash-2" class="w-4 h-4"></i>
            </button>
          </div>
        </td>
      </tr>
    `).join('');

    initIcons();
  } catch (err) {
    console.error('Error loading customers:', err);
    tbody.innerHTML = `<tr><td colspan="7" class="px-5 py-8 text-center text-rose-500">Failed to load customers.</td></tr>`;
  }
}

async function handleCreateCustomer(e) {
  e.preventDefault();
  const name = document.getElementById('cust-name').value;
  const email = document.getElementById('cust-email').value;
  const phone = document.getElementById('cust-phone').value;
  const address = document.getElementById('cust-address').value;
  const city = document.getElementById('cust-city').value;
  const notes = document.getElementById('cust-notes').value;

  try {
    const res = await fetch('/api/customers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, phone, address, city, notes })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`Customer '${data.name}' created successfully!`, 'success');
      closeModal('create-customer-modal');
      document.getElementById('create-customer-form').reset();
      loadCustomers();
      loadDashboard();
    } else {
      showToast(data.error || 'Failed to create customer', 'error');
    }
  } catch (err) {
    showToast('Network error while creating customer', 'error');
  }
}

function openEditCustomer(customerId) {
  const c = cachedCustomers.find(item => item.customer_id === customerId);
  if (!c) return;

  document.getElementById('edit-cust-id').value = c.customer_id;
  document.getElementById('edit-cust-name').value = c.name || '';
  document.getElementById('edit-cust-email').value = c.email || '';
  document.getElementById('edit-cust-phone').value = c.phone || '';
  document.getElementById('edit-cust-address').value = c.address || '';
  document.getElementById('edit-cust-city').value = c.city || '';
  document.getElementById('edit-cust-notes').value = c.notes || '';

  openModal('edit-customer-modal');
}

async function handleUpdateCustomer(e) {
  e.preventDefault();
  const customerId = document.getElementById('edit-cust-id').value;
  const payload = {
    name: document.getElementById('edit-cust-name').value,
    email: document.getElementById('edit-cust-email').value,
    phone: document.getElementById('edit-cust-phone').value,
    address: document.getElementById('edit-cust-address').value,
    city: document.getElementById('edit-cust-city').value,
    notes: document.getElementById('edit-cust-notes').value
  };

  try {
    const res = await fetch(`/api/customers/${customerId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`Customer '${data.name}' updated successfully!`, 'success');
      closeModal('edit-customer-modal');
      loadCustomers();
    } else {
      showToast(data.error || 'Failed to update customer', 'error');
    }
  } catch (err) {
    showToast('Network error while updating customer', 'error');
  }
}

async function openCustomerProfile(customerId) {
  try {
    const res = await fetch(`/api/customers/${customerId}`);
    const c = await res.json();
    if (!res.ok) {
      showToast(c.error || 'Customer not found', 'error');
      return;
    }

    document.getElementById('cust-profile-name').innerText = c.name;
    document.getElementById('cust-profile-meta').innerText = `${c.email} &bull; ${c.phone || 'No phone'} &bull; ${c.address || ''}`;
    document.getElementById('cust-profile-id').innerText = c.customer_id;
    document.getElementById('cust-profile-city').innerText = c.city || 'N/A';
    
    const orders = c.orders || [];
    document.getElementById('cust-profile-order-count').innerText = orders.length;
    const spent = orders.filter(o => o.status !== 'Cancelled').reduce((acc, cur) => acc + (cur.total || 0), 0);
    document.getElementById('cust-profile-total-spent').innerText = `$${formatMoney(spent)}`;

    const tbody = document.getElementById('cust-profile-orders-list');
    if (orders.length > 0) {
      tbody.innerHTML = orders.map(o => `
        <tr class="hover:bg-slate-50">
          <td class="px-4 py-2 font-mono font-semibold text-brand-600">${escapeHtml(o.order_number)}</td>
          <td class="px-4 py-2 text-slate-500">${formatDate(o.created_at)}</td>
          <td class="px-3 py-2">${o.items?.length || 0} item(s)</td>
          <td class="px-4 py-2 text-right font-bold">$${formatMoney(o.total)}</td>
          <td class="px-3 py-2">${getStatusBadge(o.status)}</td>
          <td class="px-3 py-2 text-right">
            <button onclick="closeModal('customer-profile-modal'); viewOrderInvoice('${o.order_number}')" 
                    class="text-xs font-semibold text-brand-600 hover:underline">
              View
            </button>
          </td>
        </tr>
      `).join('');
    } else {
      tbody.innerHTML = `<tr><td colspan="6" class="px-4 py-6 text-center text-slate-400">No orders placed by this customer yet.</td></tr>`;
    }

    openModal('customer-profile-modal');
  } catch (err) {
    showToast('Failed to load customer profile', 'error');
  }
}

async function confirmDeleteCustomer(customerId) {
  const c = cachedCustomers.find(item => item.customer_id === customerId);
  const name = c ? c.name : customerId;
  if (!confirm(`Are you sure you want to delete customer '${name}' (${customerId})? This cannot be undone.`)) {
    return;
  }
  try {
    const res = await fetch(`/api/customers/${customerId}`, { method: 'DELETE' });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      loadCustomers();
      loadDashboard();
    } else {
      showToast(data.error || 'Failed to delete customer', 'error');
    }
  } catch (err) {
    showToast('Network error while deleting customer', 'error');
  }
}

// -------------------------------------------------------------
// Items Operations
// -------------------------------------------------------------
async function loadItems() {
  const searchInput = document.getElementById('items-search');
  const catFilter = document.getElementById('items-category-filter');
  const query = searchInput ? searchInput.value.trim() : '';
  const category = catFilter ? catFilter.value : 'all';
  const tbody = document.getElementById('items-table-body');

  try {
    const res = await fetch(`/api/items?search=${encodeURIComponent(query)}&category=${encodeURIComponent(category)}`);
    const items = await res.json();
    cachedItems = items;

    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="px-5 py-8 text-center text-slate-400">No items found matching criteria.</td></tr>`;
      return;
    }

    tbody.innerHTML = items.map(it => {
      let stockBadgeClass = 'badge-success';
      let stockLabel = 'In Stock';
      if (it.stock_status === 'out_of_stock') {
        stockBadgeClass = 'badge-danger';
        stockLabel = 'Out of Stock';
      } else if (it.stock_status === 'low_stock') {
        stockBadgeClass = 'badge-warning';
        stockLabel = 'Low Stock';
      }

      return `
        <tr class="hover:bg-slate-50 transition">
          <td class="px-5 py-3 font-mono font-semibold text-xs text-brand-600">${escapeHtml(it.item_code)}</td>
          <td class="px-5 py-3">
            <p class="font-semibold text-slate-900">${escapeHtml(it.name)}</p>
            <p class="text-xs text-slate-500 line-clamp-1">${escapeHtml(it.description || '')}</p>
          </td>
          <td class="px-4 py-3">
            <span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-slate-100 text-slate-700">
              ${escapeHtml(it.category || 'General')}
            </span>
          </td>
          <td class="px-4 py-3 text-right font-bold text-slate-900">$${formatMoney(it.price)}</td>
          <td class="px-4 py-3 text-center">
            <span class="font-semibold text-sm ${it.stock <= 5 ? 'text-amber-600' : 'text-slate-800'}">${it.stock}</span>
          </td>
          <td class="px-4 py-3">
            <span class="badge ${stockBadgeClass}">${stockLabel}</span>
          </td>
          <td class="px-5 py-3 text-right whitespace-nowrap">
            <div class="inline-flex items-center gap-1.5">
              <button onclick="openEditItem('${it.item_code}')" title="Edit Item" 
                      class="p-1.5 text-slate-500 hover:text-amber-600 hover:bg-slate-100 rounded-md transition">
                <i data-lucide="edit-2" class="w-4 h-4"></i>
              </button>
              <button onclick="confirmDeleteItem('${it.item_code}')" title="Delete Item" 
                      class="p-1.5 text-slate-500 hover:text-rose-600 hover:bg-slate-100 rounded-md transition">
                <i data-lucide="trash-2" class="w-4 h-4"></i>
              </button>
            </div>
          </td>
        </tr>
      `;
    }).join('');

    initIcons();
  } catch (err) {
    console.error('Error loading items:', err);
    tbody.innerHTML = `<tr><td colspan="7" class="px-5 py-8 text-center text-rose-500">Failed to load items.</td></tr>`;
  }
}

async function handleCreateItem(e) {
  e.preventDefault();
  const payload = {
    item_code: document.getElementById('item-code').value.trim(),
    category: document.getElementById('item-category').value,
    name: document.getElementById('item-name').value.trim(),
    price: parseFloat(document.getElementById('item-price').value),
    stock: parseInt(document.getElementById('item-stock').value),
    description: document.getElementById('item-description').value.trim()
  };

  try {
    const res = await fetch('/api/items', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`Item '${data.name}' (${data.item_code}) created successfully!`, 'success');
      closeModal('create-item-modal');
      document.getElementById('create-item-form').reset();
      loadItems();
      loadDashboard();
    } else {
      showToast(data.error || 'Failed to create item', 'error');
    }
  } catch (err) {
    showToast('Network error while creating item', 'error');
  }
}

function openEditItem(itemCode) {
  const it = cachedItems.find(item => item.item_code === itemCode);
  if (!it) return;

  document.getElementById('edit-item-code').value = it.item_code;
  document.getElementById('edit-item-name').value = it.name || '';
  document.getElementById('edit-item-category').value = it.category || 'General';
  document.getElementById('edit-item-price').value = it.price || 0;
  document.getElementById('edit-item-stock').value = it.stock || 0;
  document.getElementById('edit-item-description').value = it.description || '';

  openModal('edit-item-modal');
}

async function handleUpdateItem(e) {
  e.preventDefault();
  const itemCode = document.getElementById('edit-item-code').value;
  const payload = {
    name: document.getElementById('edit-item-name').value.trim(),
    category: document.getElementById('edit-item-category').value,
    price: parseFloat(document.getElementById('edit-item-price').value),
    stock: parseInt(document.getElementById('edit-item-stock').value),
    description: document.getElementById('edit-item-description').value.trim()
  };

  try {
    const res = await fetch(`/api/items/${itemCode}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`Item '${data.item_code}' updated successfully!`, 'success');
      closeModal('edit-item-modal');
      loadItems();
      loadDashboard();
    } else {
      showToast(data.error || 'Failed to update item', 'error');
    }
  } catch (err) {
    showToast('Network error while updating item', 'error');
  }
}

async function confirmDeleteItem(itemCode) {
  const it = cachedItems.find(i => i.item_code === itemCode);
  const name = it ? it.name : itemCode;
  if (!confirm(`Are you sure you want to delete item '${name}' (${itemCode})?`)) {
    return;
  }
  try {
    const res = await fetch(`/api/items/${itemCode}`, { method: 'DELETE' });
    const data = await res.json();
    if (res.ok) {
      showToast(data.message, 'success');
      loadItems();
      loadDashboard();
    } else {
      showToast(data.error || 'Failed to delete item', 'error');
    }
  } catch (err) {
    showToast('Network error while deleting item', 'error');
  }
}

// -------------------------------------------------------------
// Orders Operations
// -------------------------------------------------------------
async function loadOrders() {
  const searchInput = document.getElementById('orders-search');
  const statusFilter = document.getElementById('orders-status-filter');
  const query = searchInput ? searchInput.value.trim() : '';
  const status = statusFilter ? statusFilter.value : 'all';
  const tbody = document.getElementById('orders-table-body');

  try {
    const res = await fetch(`/api/orders?search=${encodeURIComponent(query)}&status=${encodeURIComponent(status)}`);
    const orders = await res.json();

    if (orders.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" class="px-5 py-8 text-center text-slate-400">No orders found matching criteria.</td></tr>`;
      return;
    }

    tbody.innerHTML = orders.map(o => `
      <tr class="hover:bg-slate-50 transition">
        <td class="px-5 py-3 font-mono font-semibold text-xs text-brand-600">${escapeHtml(o.order_number)}</td>
        <td class="px-5 py-3">
          <p class="font-semibold text-slate-900">${escapeHtml(o.customer_name)}</p>
          <p class="text-xs text-slate-500">${escapeHtml(o.customer_email || '')}</p>
        </td>
        <td class="px-4 py-3 text-xs text-slate-500">${formatDate(o.created_at)}</td>
        <td class="px-4 py-3 text-center">
          <span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700">
            ${o.item_count || o.items?.length || 0}
          </span>
        </td>
        <td class="px-4 py-3 text-right font-bold text-slate-900 text-sm">$${formatMoney(o.total)}</td>
        <td class="px-4 py-3">${getPaymentBadge(o.payment_status)}</td>
        <td class="px-4 py-3">${getStatusBadge(o.status)}</td>
        <td class="px-5 py-3 text-right whitespace-nowrap">
          <div class="inline-flex items-center gap-1.5">
            <button onclick="viewOrderInvoice('${o.order_number}')" title="View / Print Invoice" 
                    class="px-2.5 py-1 text-xs font-semibold text-brand-600 bg-brand-50 hover:bg-brand-100 rounded-md transition flex items-center gap-1">
              <i data-lucide="file-text" class="w-3.5 h-3.5"></i> Invoice
            </button>
            <button onclick="openUpdateStatusModal('${o.order_number}', '${o.status}', '${o.payment_status}')" title="Change Status" 
                    class="p-1 text-slate-500 hover:text-slate-800 hover:bg-slate-100 rounded-md transition">
              <i data-lucide="more-vertical" class="w-4 h-4"></i>
            </button>
          </div>
        </td>
      </tr>
    `).join('');

    initIcons();
  } catch (err) {
    console.error('Error loading orders:', err);
    tbody.innerHTML = `<tr><td colspan="8" class="px-5 py-8 text-center text-rose-500">Failed to load orders.</td></tr>`;
  }
}

// -------------------------------------------------------------
// Interactive Order Creation Workflow
// -------------------------------------------------------------
async function initCreateOrderModal() {
  orderCart = [];
  renderOrderCart();

  // Populate Customer Select
  const custSelect = document.getElementById('order-customer-select');
  custSelect.innerHTML = '<option value="">-- Choose Customer --</option>';

  try {
    const res = await fetch('/api/customers');
    const customers = await res.json();
    cachedCustomers = customers;

    customers.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.customer_id;
      opt.innerText = `${c.name} (${c.customer_id}) - ${c.email}`;
      custSelect.appendChild(opt);
    });
  } catch (e) {
    console.error(e);
  }

  // Populate Item Picker
  const itemSelect = document.getElementById('order-item-picker');
  itemSelect.innerHTML = '<option value="">-- Select Product --</option>';

  try {
    const res = await fetch('/api/items');
    const items = await res.json();
    cachedItems = items;

    items.forEach(it => {
      const opt = document.createElement('option');
      opt.value = it.item_code;
      opt.innerText = `[${it.item_code}] ${it.name} - $${formatMoney(it.price)} (Stock: ${it.stock})`;
      if (it.stock <= 0) opt.disabled = true;
      itemSelect.appendChild(opt);
    });
  } catch (e) {
    console.error(e);
  }

  onOrderCustomerChange();
  onOrderItemSelect();
  recalculateOrderSummary();
}

function onOrderCustomerChange() {
  const sel = document.getElementById('order-customer-select');
  const preview = document.getElementById('order-customer-preview');
  const custId = sel.value;

  if (!custId) {
    preview.classList.add('hidden');
    return;
  }

  const c = cachedCustomers.find(item => item.customer_id === custId);
  if (c) {
    preview.classList.remove('hidden');
    document.getElementById('order-cust-email').innerText = c.email || 'No email';
    document.getElementById('order-cust-phone').innerText = c.phone || 'No phone';
    document.getElementById('order-cust-city').innerText = c.city || c.address || 'No address';
  }
}

function onOrderItemSelect() {
  const sel = document.getElementById('order-item-picker');
  const preview = document.getElementById('order-item-stock-preview');
  const itemCode = sel.value;
  const qtyInput = document.getElementById('order-item-qty');

  if (!itemCode) {
    preview.innerText = '';
    return;
  }

  const it = cachedItems.find(i => i.item_code === itemCode);
  if (it) {
    qtyInput.max = it.stock;
    if (it.stock > 0) {
      preview.innerHTML = `<span class="text-emerald-600 font-medium">Available stock: ${it.stock} units</span> &bull; Unit price: $${formatMoney(it.price)}`;
    } else {
      preview.innerHTML = `<span class="text-rose-600 font-bold">Out of stock!</span>`;
    }
  }
}

function addItemToOrderCart() {
  const sel = document.getElementById('order-item-picker');
  const qtyInput = document.getElementById('order-item-qty');
  const itemCode = sel.value;
  const qty = parseInt(qtyInput.value) || 1;

  if (!itemCode) {
    showToast('Please select a product first', 'warning');
    return;
  }

  const it = cachedItems.find(i => i.item_code === itemCode);
  if (!it) return;

  if (qty <= 0) {
    showToast('Quantity must be greater than zero', 'warning');
    return;
  }

  // Check if already in cart
  const existing = orderCart.find(c => c.item_code === itemCode);
  const totalWanted = (existing ? existing.quantity : 0) + qty;

  if (totalWanted > it.stock) {
    showToast(`Insufficient stock! Only ${it.stock} units available for '${it.name}'.`, 'error');
    return;
  }

  if (existing) {
    existing.quantity += qty;
    existing.subtotal = round2(existing.quantity * existing.price);
  } else {
    orderCart.push({
      item_code: it.item_code,
      name: it.name,
      category: it.category,
      price: it.price,
      quantity: qty,
      maxStock: it.stock,
      subtotal: round2(qty * it.price)
    });
  }

  qtyInput.value = 1;
  renderOrderCart();
  recalculateOrderSummary();
}

function removeCartItem(index) {
  orderCart.splice(index, 1);
  renderOrderCart();
  recalculateOrderSummary();
}

function updateCartQty(index, newQty) {
  const qty = parseInt(newQty);
  if (isNaN(qty) || qty <= 0) {
    showToast('Quantity must be at least 1', 'warning');
    renderOrderCart();
    return;
  }
  const item = orderCart[index];
  if (qty > item.maxStock) {
    showToast(`Cannot exceed available stock of ${item.maxStock}`, 'error');
    renderOrderCart();
    return;
  }
  item.quantity = qty;
  item.subtotal = round2(item.quantity * item.price);
  renderOrderCart();
  recalculateOrderSummary();
}

function renderOrderCart() {
  const tbody = document.getElementById('order-cart-table-body');
  if (orderCart.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" class="px-4 py-6 text-center text-slate-400">No items added yet. Choose a product above.</td></tr>`;
    return;
  }

  tbody.innerHTML = orderCart.map((it, idx) => `
    <tr class="hover:bg-slate-50 transition">
      <td class="px-4 py-2.5">
        <p class="font-semibold text-slate-800">${escapeHtml(it.name)}</p>
        <p class="text-[11px] text-slate-400 font-mono">${escapeHtml(it.item_code)}</p>
      </td>
      <td class="px-3 py-2.5 text-right font-medium text-slate-700">$${formatMoney(it.price)}</td>
      <td class="px-3 py-2.5 text-center">
        <input type="number" min="1" max="${it.maxStock}" value="${it.quantity}" 
               onchange="updateCartQty(${idx}, this.value)"
               class="w-14 px-1.5 py-1 text-center text-xs border border-slate-300 rounded bg-white font-semibold">
      </td>
      <td class="px-3 py-2.5 text-right font-bold text-slate-900">$${formatMoney(it.subtotal)}</td>
      <td class="px-3 py-2.5 text-center">
        <button onclick="removeCartItem(${idx})" class="text-slate-400 hover:text-rose-600 transition p-1">
          <i data-lucide="trash" class="w-3.5 h-3.5"></i>
        </button>
      </td>
    </tr>
  `).join('');

  initIcons();
}

function recalculateOrderSummary() {
  const subtotal = orderCart.reduce((sum, item) => sum + item.subtotal, 0);
  const discountPct = parseFloat(document.getElementById('order-discount-pct').value) || 0;
  const taxPct = parseFloat(document.getElementById('order-tax-pct').value) || 0;

  const discountAmount = round2(subtotal * (discountPct / 100));
  const taxable = Math.max(0, subtotal - discountAmount);
  const taxAmount = round2(taxable * (taxPct / 100));
  const grandTotal = round2(taxable + taxAmount);

  document.getElementById('order-calc-subtotal').innerText = `$${formatMoney(subtotal)}`;
  document.getElementById('order-calc-discount').innerText = `-$${formatMoney(discountAmount)}`;
  document.getElementById('order-calc-tax').innerText = `+$${formatMoney(taxAmount)}`;
  document.getElementById('order-calc-grand-total').innerText = `$${formatMoney(grandTotal)}`;
}

async function handlePlaceOrder() {
  const customerId = document.getElementById('order-customer-select').value;
  if (!customerId) {
    showToast('Please select a customer for this order', 'warning');
    return;
  }

  if (orderCart.length === 0) {
    showToast('Please add at least one product to the order', 'warning');
    return;
  }

  const payload = {
    customer_id: customerId,
    items: orderCart.map(c => ({ item_code: c.item_code, quantity: c.quantity })),
    discount_pct: parseFloat(document.getElementById('order-discount-pct').value) || 0,
    tax_pct: parseFloat(document.getElementById('order-tax-pct').value) || 0,
    status: document.getElementById('order-status-input').value,
    payment_status: document.getElementById('order-payment-input').value,
    notes: document.getElementById('order-notes-input').value.trim()
  };

  try {
    const res = await fetch('/api/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`Order '${data.order_number}' placed successfully! Total: $${formatMoney(data.total)}`, 'success');
      closeModal('create-order-modal');
      // Reset order cart & inputs
      orderCart = [];
      renderOrderCart();
      const notesEl = document.getElementById('order-notes-input');
      if (notesEl) notesEl.value = '';
      const discEl = document.getElementById('order-discount-pct');
      if (discEl) discEl.value = '0';
      const taxEl = document.getElementById('order-tax-pct');
      if (taxEl) taxEl.value = '5';
      recalculateOrderSummary();
      loadOrders();
      loadItems(); // refresh updated stock counts
      loadDashboard();
      
      // Auto open printable invoice preview
      setTimeout(() => {
        viewOrderInvoice(data.order_number);
      }, 300);
    } else {
      showToast(data.error || 'Failed to place order', 'error');
    }
  } catch (err) {
    showToast('Network error while placing order', 'error');
  }
}

// -------------------------------------------------------------
// Invoice & Status Updates
// -------------------------------------------------------------
async function viewOrderInvoice(orderNumber) {
  try {
    const res = await fetch(`/api/orders/${orderNumber}`);
    const order = await res.json();
    if (!res.ok) {
      showToast(order.error || 'Order not found', 'error');
      return;
    }

    document.getElementById('inv-order-number').innerText = order.order_number;
    document.getElementById('inv-order-date').innerText = `Date: ${formatDate(order.created_at)}`;
    document.getElementById('inv-cust-name').innerText = order.customer_name;
    document.getElementById('inv-cust-email').innerText = order.customer_email || '';
    document.getElementById('inv-cust-phone').innerText = order.customer_phone || '';
    document.getElementById('inv-cust-address').innerText = `${order.customer_address || ''} ${order.customer_city || ''}`.trim() || 'Address on file';
    
    document.getElementById('inv-order-status').className = `badge ${getStatusBadgeClass(order.status)}`;
    document.getElementById('inv-order-status').innerText = order.status;
    document.getElementById('inv-order-payment').className = `badge ${getPaymentBadgeClass(order.payment_status)}`;
    document.getElementById('inv-order-payment').innerText = order.payment_status;

    // Items
    const itemsTbody = document.getElementById('inv-items-table');
    itemsTbody.innerHTML = order.items.map(it => `
      <tr>
        <td class="px-4 py-2 font-mono text-slate-500">${escapeHtml(it.item_code)}</td>
        <td class="px-4 py-2 font-medium text-slate-900">${escapeHtml(it.name)}</td>
        <td class="px-4 py-2 text-right">$${formatMoney(it.price)}</td>
        <td class="px-4 py-2 text-center font-semibold">${it.quantity}</td>
        <td class="px-4 py-2 text-right font-bold text-slate-900">$${formatMoney(it.subtotal)}</td>
      </tr>
    `).join('');

    document.getElementById('inv-subtotal').innerText = `$${formatMoney(order.subtotal)}`;
    document.getElementById('inv-discount').innerText = `-$${formatMoney(order.discount_amount)} (${order.discount_pct}%)`;
    document.getElementById('inv-tax').innerText = `+$${formatMoney(order.tax_amount)} (${order.tax_pct}%)`;
    document.getElementById('inv-grand-total').innerText = `$${formatMoney(order.total)}`;

    if (order.notes) {
      document.getElementById('inv-notes-container').classList.remove('hidden');
      document.getElementById('inv-notes').innerText = order.notes;
    } else {
      document.getElementById('inv-notes-container').classList.add('hidden');
    }

    openModal('invoice-modal');
  } catch (err) {
    showToast('Failed to load order invoice', 'error');
  }
}

function openUpdateStatusModal(orderNumber, currentStatus, currentPayment) {
  document.getElementById('status-modal-order-number').value = orderNumber;
  document.getElementById('status-modal-order-title').innerText = `Updating order ${orderNumber}`;
  document.getElementById('status-select-order').value = currentStatus || 'Processing';
  document.getElementById('status-select-payment').value = currentPayment || 'Paid';
  openModal('update-status-modal');
}

async function handleSaveOrderStatus(e) {
  e.preventDefault();
  const orderNumber = document.getElementById('status-modal-order-number').value;
  const status = document.getElementById('status-select-order').value;
  const payment_status = document.getElementById('status-select-payment').value;

  try {
    const res = await fetch(`/api/orders/${orderNumber}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, payment_status })
    });
    const data = await res.json();
    if (res.ok) {
      showToast(`Order ${orderNumber} updated to ${status}!`, 'success');
      closeModal('update-status-modal');
      loadOrders();
      loadItems();
      loadDashboard();
    } else {
      showToast(data.error || 'Failed to update order status', 'error');
    }
  } catch (err) {
    showToast('Network error while updating status', 'error');
  }
}

// -------------------------------------------------------------
// UI Helpers & Formatters
// -------------------------------------------------------------
function formatMoney(amount) {
  return (parseFloat(amount) || 0).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  });
}

function formatDate(isoStr) {
  if (!isoStr) return '-';
  try {
    const d = new Date(isoStr);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch {
    return isoStr;
  }
}

function round2(val) {
  return Math.round((val + Number.EPSILON) * 100) / 100;
}

function escapeHtml(text) {
  if (!text) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function debounce(func, wait) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

function getStatusBadgeClass(status) {
  switch ((status || '').toLowerCase()) {
    case 'completed': return 'badge-success';
    case 'processing': return 'badge-info';
    case 'pending': return 'badge-warning';
    case 'cancelled': return 'badge-danger';
    default: return 'badge-purple';
  }
}

function getStatusBadge(status) {
  const cls = getStatusBadgeClass(status);
  return `<span class="badge ${cls}">${escapeHtml(status || 'Unknown')}</span>`;
}

function getPaymentBadgeClass(status) {
  switch ((status || '').toLowerCase()) {
    case 'paid': return 'badge-success';
    case 'pending': return 'badge-warning';
    case 'partial': return 'badge-info';
    case 'refunded': return 'badge-danger';
    default: return 'badge-purple';
  }
}

function getPaymentBadge(status) {
  const cls = getPaymentBadgeClass(status);
  return `<span class="badge ${cls}">${escapeHtml(status || 'Pending')}</span>`;
}
