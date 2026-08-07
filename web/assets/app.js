const grid = document.querySelector('#asset-grid');
const count = document.querySelector('#asset-count');
const health = document.querySelector('#health');
const form = document.querySelector('#asset-form');
const error = document.querySelector('#form-error');
const ruleForm = document.querySelector('#rule-form');
const ruleError = document.querySelector('#rule-error');
const ruleAsset = document.querySelector('#rule-asset');
const ruleKind = document.querySelector('#rule-kind');
const thresholdField = document.querySelector('#threshold-field');
const queryInput = document.querySelector('#asset-query');
const searchBtn = document.querySelector('#search-btn');
const candidateSelect = document.querySelector('#asset-candidate');
const searchHint = document.querySelector('#search-hint');
const report = document.querySelector('#report');
const runMonitor = document.querySelector('#run-monitor');
const schedulerNodes = document.querySelector('#scheduler-nodes');
const schedulerNext = document.querySelector('#scheduler-next');
const channelList = document.querySelector('#channel-list');
const channelCount = document.querySelector('#channel-count');
const channelForm = document.querySelector('#channel-form');
const channelError = document.querySelector('#channel-error');
const channelType = document.querySelector('#channel-type');
const ghConfig = document.querySelector('#gh-config');
const ghSync = document.querySelector('#gh-sync');
const ghStatus = document.querySelector('#gh-status');
const ghRepo = document.querySelector('#gh-repo');
const ghToken = document.querySelector('#gh-token');
const ghCopy = document.querySelector('#gh-copy');

async function request(path, options = {}) {
  const response = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options });
  if (!response.ok) {
    throw new Error((await response.json().catch(() => ({}))).detail || '请求失败');
  }
  return response.status === 204 ? null : response.json();
}

function escapeHtml(value) {
  const node = document.createElement('span');
  node.textContent = value;
  return node.innerHTML;
}

function formatTime(iso) {
  if (!iso) return '未监控';
  const d = new Date(iso);
  const pad = n => String(n).padStart(2, '0');
  return `${d.getMonth() + 1}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function renderFunds(overview, assets) {
  count.textContent = overview.length;
  ruleAsset.innerHTML = assets.map(asset => `<option value="${asset.id}">${escapeHtml(asset.name)}</option>`).join('');
  if (!overview.length) {
    grid.innerHTML = '<p class="empty">还没有基金。请在右侧搜索添加。</p>';
    return;
  }
  grid.innerHTML = overview.map(item => {
    const number = item.change_percent === null ? null : parseFloat(item.change_percent);
    const cls = number === null ? '' : (number >= 0 ? 'up' : 'down');
    const arrow = number === null ? '' : (number > 0 ? '↑' : number < 0 ? '↓' : '');
    const changeText = number === null ? '—' : `${number >= 0 ? '+' : ''}${number.toFixed(2)}% ${arrow}`;
    const kindLabel = { fund: '基金', etf: 'ETF', cn_index: '指数', global_index: '海外指数' }[item.kind] || item.kind;
    return `<article class="fund-card"><div class="fund-head"><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.code)} · ${escapeHtml(kindLabel)}</small></div>` +
      `<div class="fund-price ${cls}">${item.value ?? '-'}</div>` +
      `<div class="fund-change ${cls}">${changeText}</div>` +
      `<div class="fund-meta">${formatTime(item.observed_at)} · ${escapeHtml(item.source || '-')}</div>` +
      `<div class="fund-actions"><button class="check" data-check="${item.id}" type="button">检查</button><button data-id="${item.id}" type="button">删除</button></div></article>`;
  }).join('');
  grid.querySelectorAll('[data-id]').forEach(button => button.addEventListener('click', async () => {
    await request(`/api/v1/assets/${button.dataset.id}`, { method: 'DELETE' });
    await load();
  }));
  grid.querySelectorAll('[data-check]').forEach(button => button.addEventListener('click', async () => {
    button.disabled = true;
    button.textContent = '检查中';
    try {
      const result = await request(`/api/v1/assets/${button.dataset.check}/check`, { method: 'POST' });
      health.textContent = result.error ? `来源异常：${result.error}` : `检查完成：${result.source}`;
      await load();
    } catch (exception) {
      health.textContent = exception.message;
    } finally {
      button.disabled = false;
      button.textContent = '检查';
    }
  }));
}

function renderChannels(channels) {
  channelCount.textContent = channels.length;
  if (!channels.length) {
    channelList.innerHTML = '<p class="empty">还没有推送通道。告警默认只显示在监控报告里。</p>';
    return;
  }
  channelList.innerHTML = channels.map(channel =>
    `<article class="asset"><div><strong>${escapeHtml(channel.name)}</strong><small>${escapeHtml(channel.channel_type)} · ${escapeHtml(channel.enabled ? '已启用' : '已停用')}</small></div>` +
    `<div><button class="test" data-test="${channel.id}" type="button">测试</button><button data-channel="${channel.id}" type="button">删除</button></div></article>`
  ).join('');
  channelList.querySelectorAll('[data-channel]').forEach(button => button.addEventListener('click', async () => {
    await request(`/api/v1/channels/${button.dataset.channel}`, { method: 'DELETE' });
    await load();
  }));
  channelList.querySelectorAll('[data-test]').forEach(button => button.addEventListener('click', async () => {
    button.disabled = true;
    button.textContent = '发送中…';
    try {
      const result = await request(`/api/v1/channels/${button.dataset.test}/test`, { method: 'POST' });
      health.textContent = result.ok ? '测试通知发送成功 ✅' : `测试失败：${result.detail || result.status}`;
    } catch (exception) {
      health.textContent = `测试失败：${exception.message}`;
    } finally {
      button.disabled = false;
      button.textContent = '测试';
    }
  }));
}

function renderScheduler(status) {
  const times = status.schedule_times || [];
  schedulerNodes.textContent = times.length ? `节点：${times.join(' / ')}` : '';
  if (status.running) {
    schedulerNext.textContent = status.next_due_at ? `下次执行：${new Date(status.next_due_at).toLocaleString('zh-CN')}` : '运行中';
  } else {
    schedulerNext.textContent = '定时任务未启动';
  }
}

function renderReport(result) {
  if (result && result.text) {
    report.innerHTML = `<pre class="report-text">${escapeHtml(result.text)}</pre>`;
  } else {
    report.innerHTML = '<p class="empty">无报告。</p>';
  }
}

async function load() {
  try {
    const [status, overview, assets, scheduler, channels, ghconfig] = await Promise.all([
      request('/api/health'),
      request('/api/v1/assets/overview'),
      request('/api/v1/assets'),
      request('/api/v1/monitor/status'),
      request('/api/v1/channels'),
      request('/api/v1/ghconfig'),
    ]);
    health.textContent = status.status === 'healthy' ? '服务运行正常' : '服务需要注意';
    renderFunds(overview, assets);
    renderScheduler(scheduler);
    renderChannels(channels);
    ghConfig.textContent = ghconfig.content || '（暂无资产）';
    if (!ghRepo.value && ghconfig.repo) {
      ghRepo.value = ghconfig.repo;
    }
  } catch (exception) {
    health.textContent = '服务不可用';
    grid.innerHTML = '<p class="empty">无法读取本地服务，请重启应用后重试。</p>';
  }
}

async function searchAssets() {
  const query = queryInput.value.trim();
  if (!query) return;
  searchHint.textContent = '搜索中…';
  searchBtn.disabled = true;
  try {
    const results = await request(`/api/v1/search?q=${encodeURIComponent(query)}`);
    candidateSelect.innerHTML = '<option value="">请选择匹配项</option>' +
      results.map(item => {
        const hints = (item.ticker_hints || []).join(' / ');
        const meta = hints || item.description || item.kind;
        return `<option value="${item.code}" data-name="${escapeHtml(item.name)}" data-kind="${item.kind}" data-identifiers='${escapeHtml(JSON.stringify(item.identifiers || {}))}'>${escapeHtml(item.name)}（${escapeHtml(item.code)} · ${escapeHtml(meta)}）</option>`;
      }).join('');
    candidateSelect.disabled = results.length === 0;
    searchHint.textContent = results.length ? `找到 ${results.length} 个匹配，请选择：` : '未找到匹配项，请尝试其他关键词。';
  } catch (exception) {
    searchHint.textContent = `搜索失败：${exception.message}`;
  } finally {
    searchBtn.disabled = false;
  }
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  error.textContent = '';
  const option = candidateSelect.selectedOptions[0];
  if (!option || !option.value) {
    error.textContent = '请先搜索并选择一个匹配项';
    return;
  }
  let identifiers;
  try {
    identifiers = JSON.parse(option.dataset.identifiers || '{}');
  } catch (exception) {
    identifiers = {};
  }
  if (!Object.keys(identifiers).length) {
    error.textContent = '该匹配项缺少数据源标识，请重试';
    return;
  }
  try {
    await request('/api/v1/assets', {
      method: 'POST',
      body: JSON.stringify({ name: option.dataset.name, kind: option.dataset.kind, identifiers }),
    });
    form.reset();
    candidateSelect.innerHTML = '<option value="">请先搜索</option>';
    candidateSelect.disabled = true;
    searchHint.textContent = '';
    await load();
  } catch (exception) {
    error.textContent = exception.message;
  }
});

searchBtn.addEventListener('click', searchAssets);
queryInput.addEventListener('keydown', event => {
  if (event.key === 'Enter') {
    event.preventDefault();
    searchAssets();
  }
});

ruleKind.addEventListener('change', () => {
  const needsThreshold = ['percent_change', 'nav_change'].includes(ruleKind.value);
  thresholdField.style.display = needsThreshold ? '' : 'none';
  thresholdField.querySelector('input').required = needsThreshold;
});

ruleForm.addEventListener('submit', async event => {
  event.preventDefault();
  ruleError.textContent = '';
  const data = new FormData(ruleForm);
  const assetId = data.get('asset_id');
  if (!assetId) {
    ruleError.textContent = '请先添加资产';
    return;
  }
  const kind = ruleKind.value;
  const payload = { asset_id: Number(assetId), kind, cooldown_minutes: Number(data.get('cooldown_minutes')) };
  if (['percent_change', 'nav_change'].includes(kind)) {
    payload.threshold = data.get('threshold');
  }
  try {
    await request(`/api/v1/assets/${assetId}/rules`, { method: 'POST', body: JSON.stringify(payload) });
    ruleError.textContent = '告警已保存';
    ruleForm.reset();
  } catch (exception) {
    ruleError.textContent = exception.message;
  }
});

channelType.addEventListener('change', () => {
  document.querySelectorAll('.channel-fields').forEach(field => {
    field.style.display = field.dataset.type === channelType.value ? '' : 'none';
  });
});

channelForm.addEventListener('submit', async event => {
  event.preventDefault();
  channelError.textContent = '';
  const data = new FormData(channelForm);
  const kind = data.get('channel_type');
  const settings = {};
  let secret = '';
  if (kind === 'pushplus') {
    secret = data.get('token') || '';
  } else if (kind === 'serverchan') {
    secret = data.get('send_key') || '';
  } else if (kind === 'email') {
    settings.host = data.get('host') || '';
    settings.port = data.get('port') || '465';
    settings.username = data.get('username') || '';
    settings.sender_address = data.get('sender_address') || '';
    settings.recipient = data.get('recipient') || '';
    secret = data.get('password') || '';
  } else if (kind === 'telegram') {
    settings.chat_id = data.get('chat_id') || '';
    secret = data.get('token') || '';
  } else if (kind === 'webhook') {
    settings.url = data.get('url') || '';
    secret = data.get('secret') || '';
  }
  try {
    const channel = await request('/api/v1/channels', {
      method: 'POST',
      body: JSON.stringify({ name: data.get('name'), channel_type: kind, settings }),
    });
    if (secret) {
      await request(`/api/v1/channels/${channel.id}/secret`, {
        method: 'PUT',
        body: JSON.stringify({ secret }),
      });
    }
    channelError.textContent = '通道已保存，可点击「测试」验证';
    channelForm.reset();
    await load();
  } catch (exception) {
    channelError.textContent = exception.message;
  }
});

runMonitor.addEventListener('click', async () => {
  runMonitor.disabled = true;
  runMonitor.textContent = '监控中…';
  report.innerHTML = '<p class="empty">正在执行监控，请稍候…</p>';
  try {
    const result = await request('/api/v1/monitor/run', { method: 'POST' });
    renderReport(result);
  } catch (exception) {
    report.innerHTML = `<p class="empty">监控失败：${escapeHtml(exception.message)}</p>`;
  } finally {
    runMonitor.disabled = false;
    runMonitor.textContent = '▶ 立即监控一次';
  }
});

ghSync.addEventListener('click', async () => {
  ghSync.disabled = true;
  ghSync.textContent = '同步中…';
  ghStatus.textContent = '';
  try {
    const token = ghToken.value.trim();
    if (token) {
      await request('/api/v1/ghconfig/token', { method: 'PUT', body: JSON.stringify({ secret: token }) });
      ghToken.value = '';
    }
    const result = await request('/api/v1/ghconfig/sync', {
      method: 'POST',
      body: JSON.stringify({ repo: ghRepo.value.trim() || 'Frog755/fund-monitor-headless' }),
    });
    ghStatus.textContent = result.detail || '已同步';
    ghStatus.style.color = 'var(--primary-deep)';
  } catch (exception) {
    ghStatus.textContent = `同步失败：${exception.message}。可在 GitHub 网页手动编辑 headless/config.yaml，或使用「复制配置」后粘贴。`;
    ghStatus.style.color = 'var(--up)';
  } finally {
    ghSync.disabled = false;
    ghSync.textContent = '同步到 GitHub';
  }
});

ghCopy.addEventListener('click', async () => {
  const content = ghConfig.textContent;
  try {
    await navigator.clipboard.writeText(content);
    ghStatus.textContent = '配置已复制，请到 GitHub 仓库 headless/config.yaml 粘贴并提交（Commit changes）。';
    ghStatus.style.color = 'var(--primary-deep)';
  } catch (exception) {
    ghStatus.textContent = `复制失败：${exception.message}`;
  }
});

const tabNav = document.querySelector('#tab-nav');
const tabButtons = Array.from(tabNav.querySelectorAll('button'));
const tabIndicator = document.createElement('span');
tabIndicator.className = 'tab-indicator';
tabNav.appendChild(tabIndicator);

function moveTabIndicator(button) {
  const navRect = tabNav.getBoundingClientRect();
  const btnRect = button.getBoundingClientRect();
  tabIndicator.style.width = `${btnRect.width}px`;
  tabIndicator.style.transform = `translateX(${btnRect.left - navRect.left - 6}px)`;
}

function activateTab(button) {
  tabButtons.forEach(item => item.classList.toggle('active', item === button));
  moveTabIndicator(button);
  document.querySelectorAll('.tab-content').forEach(content => {
    content.classList.toggle('active', content.id === `tab-${button.dataset.tab}`);
  });
}

tabButtons.forEach(button => button.addEventListener('click', () => activateTab(button)));
window.addEventListener('resize', () => {
  const active = tabNav.querySelector('button.active');
  if (active) moveTabIndicator(active);
});
const initialTab = tabNav.querySelector('button.active');
if (initialTab) requestAnimationFrame(() => moveTabIndicator(initialTab));

document.querySelector('#refresh').addEventListener('click', load);
load();
