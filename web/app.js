const state = {context: null, current: null, axes: null, analysis: null, queries: []};
const element = identifier => document.getElementById(identifier);

async function request(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || '请求失败');
  return value;
}

function message(value, error = false) {
  element('status').textContent = value;
  element('status').className = error ? 'error' : '';
}

async function guarded(action) {
  try { await action(); } catch (error) { message(error.message, true); }
}

function selected() {
  const selection = {};
  for (const control of state.context.product.options) selection[control[0]] = element('select-' + control[0]).value;
  selection.universe = element('universe').value;
  return {revision: element('revision').value, selection};
}

function renderControls() {
  const revision = element('revision').value || state.context.default_revision;
  element('revision').replaceChildren();
  for (const dataset of state.context.datasets) {
    const option = document.createElement('option');
    option.value = dataset.revision;
    option.textContent = dataset.label + ' · ' + dataset.revision.slice(0, 9);
    element('revision').append(option);
  }
  element('revision').value = revision;
  if (!element('revision').value) element('revision').value = state.context.default_revision;
  if (element('controls').children.length) return;
  for (const [key, labelText, choices] of state.context.product.options) {
    const label = document.createElement('label');
    label.textContent = labelText;
    const select = document.createElement('select');
    select.id = 'select-' + key;
    for (const choice of choices) {
      const option = document.createElement('option');
      option.value = choice;
      option.textContent = choice;
      select.append(option);
    }
    select.value = state.context.product.selection[key];
    label.append(select);
    element('controls').append(label);
  }
}

function fillRevisionOptions(select, value) {
  select.replaceChildren();
  for (const dataset of state.context.datasets) {
    const option = document.createElement('option');
    option.value = dataset.revision;
    option.textContent = dataset.label + ' · ' + dataset.revision.slice(0, 9);
    select.append(option);
  }
  select.value = value || state.context.default_revision;
  if (!select.value) select.value = state.context.default_revision;
}

async function refreshAxes() {
  const revision = element('revision').value || state.context.default_revision;
  try {
    state.axes = await request('/api/axes?revision=' + encodeURIComponent(revision));
  } catch (error) {
    state.axes = {axes: [], releases: []};
    throw error;
  }
  const universes = [...new Set(state.axes.releases.map(release => release.universe))];
  element('universe').replaceChildren();
  for (const value of universes) {
    const option = document.createElement('option'); option.value = value; option.textContent = value;
    element('universe').append(option);
  }
  element('universe').value = universes.includes('eligible-households')
    ? 'eligible-households' : universes[0];
  const population = element('population');
  const outcome = element('outcome');
  const keepPopulation = new Set([...population.querySelectorAll('input:checked')].map(box => box.value));
  const keepOutcome = new Set([...outcome.querySelectorAll('input:checked')].map(box => box.value));
  population.replaceChildren(); outcome.replaceChildren();
  for (const axis of state.axes.axes) {
    for (const level of axis.levels) {
      const wrapping = document.createElement('label');
      wrapping.className = 'chip';
      const box = document.createElement('input'); box.type = 'checkbox';
      box.value = axis.axis + '|' + level;
      box.name = axis.axis;
      const text = document.createElement('span');
      text.textContent = axis.axis + '=' + level;
      if (keepPopulation.has(box.value)) box.checked = true;
      box.onchange = () => enforceAxis(population, outcome, axis.axis);
      wrapping.append(box, text);
      population.append(wrapping);
      const other = document.createElement('label');
      other.className = 'chip';
      const second = document.createElement('input'); second.type = 'checkbox';
      second.value = axis.axis + '|' + level;
      second.name = axis.axis;
      const label = document.createElement('span');
      label.textContent = axis.axis + '=' + level;
      if (keepOutcome.has(second.value)) second.checked = true;
      second.onchange = () => enforceAxis(outcome, population, axis.axis);
      other.append(second, label);
      outcome.append(other);
    }
  }
}

function enforceAxis(container, other, axis) {
  const boxes = [...container.querySelectorAll('input:checked')].filter(box => box.name === axis);
  for (const box of boxes.slice(1)) box.checked = false;
  if (boxes.length) {
    for (const box of other.querySelectorAll('input')) if (box.name === axis) box.checked = false;
  }
}

function queryTerms(container) {
  return [...container.querySelectorAll('input:checked')].map(box => {
    const [axis, level] = box.value.split('|');
    return {axis, level};
  });
}

function displayValue(value) {
  if (value === null || value === undefined) return '未观测';
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(4);
  return typeof value === 'object' ? JSON.stringify(value) : String(value);
}

function roundedInterval(value) {
  if (!value) return '—';
  const low = value.low, high = value.high;
  if (low === null || high === null) return '—';
  const format = number => Number.isInteger(number) ? String(number) : number.toFixed(2);
  return format(low) + ' – ' + format(high);
}

function drawChart(series) {
  const canvas = element('chart');
  const context = canvas.getContext('2d');
  context.clearRect(0, 0, canvas.width, canvas.height);
  const values = series.filter(point => typeof point.y === 'number' && Number.isFinite(point.y));
  context.font = '12px sans-serif';
  if (!values.length) { context.fillText('该范围没有可定量的描述值', 30, 50); return; }
  const low = Math.min(0, ...values.map(point => point.y));
  const high = Math.max(1, ...values.map(point => point.y));
  const scale = value => 250 - (value - low) / (high - low || 1) * 210;
  context.strokeStyle = '#90a5ad';
  context.beginPath(); context.moveTo(45, 20); context.lineTo(45, 250); context.lineTo(940, 250); context.stroke();
  context.fillStyle = '#0a7168';
  const scatter = values.every(point => typeof point.x === 'number');
  const minimumX = scatter ? Math.min(...values.map(point => point.x)) : 0;
  const maximumX = scatter ? Math.max(...values.map(point => point.x)) : 1;
  values.forEach((point, index) => {
    const position = scatter ? 60 + (point.x - minimumX) / (maximumX - minimumX || 1) * 850 : 55 + index * 875 / values.length;
    if (scatter) {
      context.beginPath(); context.arc(position, scale(point.y), 3.5, 0, Math.PI * 2); context.fill();
    } else {
      context.fillRect(position, Math.min(scale(point.y), scale(0)), Math.max(3, 800 / values.length), Math.max(1, Math.abs(scale(point.y) - scale(0))));
    }
    if (values.length < 12) context.fillText(point.label, position, 275);
  });
  context.fillStyle = '#29434e';
  context.fillText(high.toFixed(2), 0, 45); context.fillText(low.toFixed(2), 0, 250);
  context.fillText(scatter ? '所选资料的数值坐标（仅为原始描述）' : '按表中顺序展示描述值；缺测不绘制为零', 50, 20);
}

function render(result, heading) {
  state.current = result;
  element('summary').replaceChildren();
  for (const [label, value] of Object.entries(result.view.summary)) {
    const card = document.createElement('article');
    const title = document.createElement('span'); title.textContent = label;
    const amount = document.createElement('strong'); amount.textContent = displayValue(value);
    card.append(title, amount); element('summary').append(card);
  }
  element('notes').replaceChildren();
  for (const note of result.view.notes) {
    const paragraph = document.createElement('p'); paragraph.textContent = note; element('notes').append(paragraph);
  }
  const rows = result.view.rows;
  const fields = rows.length ? Object.keys(rows[0]) : [];
  const header = document.createElement('tr');
  for (const field of fields) { const cell = document.createElement('th'); cell.textContent = field; header.append(cell); }
  element('columns').replaceChildren(header); element('rows').replaceChildren();
  for (const row of rows) {
    const line = document.createElement('tr'); line.tabIndex = 0;
    for (const field of fields) { const cell = document.createElement('td'); cell.textContent = displayValue(row[field]); line.append(cell); }
    line.onclick = () => { element('details').textContent = JSON.stringify(row, null, 2); };
    line.onkeydown = event => { if (event.key === 'Enter') line.click(); };
    element('rows').append(line);
  }
  drawChart(result.view.series);
  element('details').textContent = JSON.stringify({revision: result.revision, selection: result.selection,
    history: result.view.history || null}, null, 2);
  message((heading || '已更新描述') + ' · 数据 ' + result.revision.slice(0, 12));
}

function termsText(terms) {
  return terms.length ? terms.map(term => term.axis + '=' + term.level).join('，') : '全部户';
}

function describeStatus(status) {
  return {
    unique: '唯一可确定：现有材料下该指标只能取一个值',
    possible: '仍有多种可能：现有材料只支持一个范围',
    conflict: '材料互相冲突：联立约束无可行解，需先核对材料',
    undefined: '未定义：分母可能为零，比例不能确定',
    unsupported: '现有材料不足以回答：缺少兼容的表或维度',
  }[status] || status;
}

function percentInterval(value) {
  if (!value || !value.defined || value.low === null || value.high === null) return '—';
  return (value.low * 100).toFixed(1) + '% – ' + (value.high * 100).toFixed(1) + '%';
}

function renderAnalysis(analysis, heading) {
  element('answer').replaceChildren();
  const card = document.createElement('article');
  card.className = 'answer ' + analysis.status;
  const title = document.createElement('h3'); title.textContent = describeStatus(analysis.status);
  const line = document.createElement('p');
  line.textContent = '问题：分母 ' + termsText(analysis.query.population) + '；结果 ' +
    termsText(analysis.query.outcome) + (analysis.period ? '（' + analysis.period + '）' : '');
  const numbers = document.createElement('div'); numbers.className = 'numbers';
  for (const [label, value] of [
    ['分子（户）', roundedInterval(analysis.numerator)],
    ['分母（户）', roundedInterval(analysis.denominator)],
    ['占比', percentInterval(analysis.share)],
  ]) {
    const item = document.createElement('div');
    const name = document.createElement('span'); name.textContent = label;
    const amount = document.createElement('strong'); amount.textContent = value;
    item.append(name, amount); numbers.append(item);
  }
  card.append(title, line, numbers);
  const notes = document.createElement('div'); notes.id = 'analysis-notes';
  for (const note of analysis.notes) {
    const paragraph = document.createElement('p'); paragraph.textContent = note; notes.append(paragraph);
  }
  card.append(notes);
  element('answer').append(card);

  const evidence = element('evidence'); evidence.replaceChildren();
  const usedTitle = document.createElement('h3'); usedTitle.textContent = '回答依赖的表';
  evidence.append(usedTitle);
  if (analysis.evidence.used.length) {
    const list = document.createElement('ul');
    for (const table of analysis.evidence.used) {
      const item = document.createElement('li');
      item.textContent = table.table + ' · ' + table.release + ' · ' + table.unit + ' · ' +
        table.period + ' · ' + table.role;
      list.append(item);
    }
    evidence.append(list);
  } else {
    const none = document.createElement('p'); none.textContent = '本次没有可用的表。';
    evidence.append(none);
  }
  if (analysis.evidence.excluded.length) {
    const excludedTitle = document.createElement('h3'); excludedTitle.textContent = '未并入的表及原因';
    const list = document.createElement('ul');
    for (const excluded of analysis.evidence.excluded) {
      const item = document.createElement('li');
      item.textContent = excluded.table + '：' + excluded.reasons.join('；');
      list.append(item);
    }
    evidence.append(excludedTitle, list);
  }
  if (analysis.evidence.rules && analysis.evidence.rules.length) {
    const ruleTitle = document.createElement('h3'); ruleTitle.textContent = '结构约定';
    const list = document.createElement('ul');
    for (const rule of analysis.evidence.rules) {
      const item = document.createElement('li');
      item.textContent = rule.rule + '（' + rule.zero + '）：' + rule.effect;
      list.append(item);
    }
    evidence.append(ruleTitle, list);
  }
  if (analysis.evidence.confidence) {
    const paragraph = document.createElement('p');
    paragraph.textContent = '计算口径：' + analysis.evidence.confidence +
      '；共用 ' + analysis.evidence.cells + ' 个单元格。';
    evidence.append(paragraph);
  } else if (analysis.evidence.period) {
    const paragraph = document.createElement('p');
    paragraph.textContent = '期间口径：' + analysis.evidence.period +
      '；不同期间口径的表未并入同一可行域。';
    evidence.append(paragraph);
  }

  const conflicts = element('conflicts'); conflicts.replaceChildren();
  if (analysis.conflicts.length) {
    const title = document.createElement('h3'); title.textContent = '可核对的冲突组合';
    conflicts.append(title);
    for (const conflict of analysis.conflicts) {
      const box = document.createElement('article'); box.className = 'conflict';
      const name = document.createElement('strong');
      name.textContent = conflict.tables.join(' × ') + ' · ' + conflict.kind;
      box.append(name);
      for (const detail of conflict.details) {
        const paragraph = document.createElement('p');
        paragraph.textContent = detail.message + (detail.sources
          ? '（' + detail.sources.map(source => source.table + '：' +
              displayValue(source.implied_low) + '–' + displayValue(source.implied_high)).join('；') + '）'
          : '');
        box.append(paragraph);
      }
      conflicts.append(box);
    }
  }

  const alternatives = element('alternatives'); alternatives.replaceChildren();
  if (analysis.alternatives.length) {
    const title = document.createElement('h3'); title.textContent = '逐表贡献（去掉一张表后的分子范围）';
    const list = document.createElement('ul');
    for (const row of analysis.alternatives) {
      const item = document.createElement('li');
      item.textContent = row.removed + '：' + row.effect + '，分子 ' + roundedInterval(row.numerator);
      list.append(item);
    }
    alternatives.append(title, list);
  }
  element('details').textContent = JSON.stringify(analysis, null, 2);
  message((heading || '已分析交叉问题') + ' · ' + describeStatus(analysis.status));
}

function renderComparison(comparison, heading) {
  const columns = ['问题', '补表前占比', '补表后占比', '变化'];
  const header = document.createElement('tr');
  for (const field of columns) { const cell = document.createElement('th'); cell.textContent = field; header.append(cell); }
  element('compare-columns').replaceChildren(header);
  element('compare-rows').replaceChildren();
  for (const row of comparison.rows) {
    const line = document.createElement('tr');
    const values = [
      row.label || termsText(row.query.population) + ' → ' + termsText(row.query.outcome),
      percentInterval(row.baseline.share),
      percentInterval(row.current.share),
      row.change,
    ];
    for (const value of values) {
      const cell = document.createElement('td'); cell.textContent = value; line.append(cell);
    }
    element('compare-rows').append(line);
  }
  element('details').textContent = JSON.stringify(comparison, null, 2);
  message((heading || '已比较补表前后') + ' · ' + comparison.rows.length + ' 个问题');
}

async function refresh() {
  state.context = await request('/api/context');
  renderControls();
  await refreshAxes();
  fillRevisionOptions(element('baseline-revision'), state.context.datasets[1]
    ? state.context.datasets[1].revision : state.context.default_revision);
  element('archive').replaceChildren();
  for (const notebook of state.context.notebooks) {
    const button = document.createElement('button'); button.textContent = notebook.title + ' #' + notebook.id;
    button.onclick = () => guarded(async () => {
      const saved = await request('/api/notebooks/' + notebook.id);
      await openNotebook(saved);
    });
    element('archive').append(button);
  }
  await refreshAxes();
}

async function openNotebook(saved) {
  element('revision').value = saved.revision;
  await refreshAxes();
  for (const [key, value] of Object.entries(saved.selection)) {
    const control = element('select-' + key); if (control) control.value = value;
    if (key === 'universe') element('universe').value = value;
  }
  const payload = saved.result;
  if (payload.kind === 'identification') {
    renderAnalysis(payload.analysis, '已读取保存的证据记录 #' + saved.id);
  } else if (payload.kind === 'comparison') {
    renderComparison(payload.comparison, '已读取保存的比较记录 #' + saved.id);
  } else {
    render(saved.result, '已读取保存的描述，不随新数据变化');
  }
}

element('inspect').onclick = () => guarded(async () => {
  await refreshAxes();
  render(await request('/api/explore', selected()));
});
element('analyze').onclick = () => guarded(async () => {
  const query = {population: queryTerms(element('population')), outcome: queryTerms(element('outcome'))};
  if (!query.outcome.length) throw new Error('结果条件至少选择一项');
  const response = await request('/api/analyze', {...selected(), query});
  state.analysis = response.analysis;
  state.queries = [{label: element('query-label').value, ...query}];
  renderAnalysis(response.analysis, '已分析交叉问题');
});
element('compare').onclick = () => guarded(async () => {
  if (!state.queries.length) throw new Error('请先分析一个交叉问题');
  const current = {revision: element('revision').value, selection: selected().selection};
  const baselineSelection = {...current.selection};
  if (current.selection.release === 'supplement') baselineSelection.release = 'first';
  const baseline = {revision: element('baseline-revision').value, selection: baselineSelection};
  if (baseline.revision === current.revision) throw new Error('请选择与当前不同的补表前材料');
  const response = await request('/api/compare', {queries: state.queries, baseline, current});
  renderComparison(response.comparison, '已比较补表前后');
});
element('revision').onchange = () => guarded(async () => {
  await refreshAxes();
  render(await request('/api/explore', selected()), '已切换材料版本');
});
element('save').onclick = () => guarded(async () => {
  const saved = await request('/api/notebooks', {...selected(), title: element('title').value});
  await refresh(); render(saved.result, '已保存记录 #' + saved.id);
});
element('save-analysis').onclick = () => guarded(async () => {
  if (!state.analysis) throw new Error('请先分析一个交叉问题');
  const query = state.analysis.query;
  const saved = await request('/api/notebooks', {...selected(), title: element('title').value,
    kind: 'identification', query});
  await refresh(); renderAnalysis(saved.result.analysis, '已保存证据记录 #' + saved.id);
});
element('save-comparison').onclick = () => guarded(async () => {
  if (!state.queries.length) throw new Error('请先分析一个交叉问题');
  const current = {revision: element('revision').value, selection: selected().selection};
  const baselineSelection = {...current.selection};
  if (current.selection.release === 'supplement') baselineSelection.release = 'first';
  const baseline = {revision: element('baseline-revision').value, selection: baselineSelection};
  const saved = await request('/api/notebooks', {...selected(), title: element('title').value,
    kind: 'comparison', queries: state.queries, baseline, current});
  await refresh(); renderComparison(saved.result.comparison, '已保存比较记录 #' + saved.id);
});
element('raw').onclick = () => guarded(async () => {
  const revision = state.current ? state.current.revision : element('revision').value;
  element('details').textContent = JSON.stringify(await request('/api/data?revision=' + encodeURIComponent(revision)), null, 2);
});
element('upload').onchange = () => guarded(async () => {
  const file = element('upload').files[0]; if (!file) return;
  const data = JSON.parse(await file.text());
  const uploaded = await request('/api/datasets', {label: file.name, data});
  await refresh(); element('revision').value = uploaded.revision;
  render(await request('/api/explore', selected()), '已导入独立数据版本');
});
element('export').onclick = () => guarded(async () => {
  if (!state.current) throw new Error('请先查看一个范围');
  const data = await request('/api/data?revision=' + encodeURIComponent(state.current.revision));
  const blob = new Blob([JSON.stringify({description: state.current, data}, null, 2)], {type: 'application/json'});
  const url = URL.createObjectURL(blob); const link = document.createElement('a');
  link.href = url; link.download = 'analysis-' + state.current.revision.slice(0, 12) + '.json'; link.click();
  URL.revokeObjectURL(url);
});
guarded(async () => {
  await refresh();
  element('population').querySelectorAll('input').forEach(box => {
    if (box.value === 'income|low') box.checked = true;
  });
  element('outcome').querySelectorAll('input').forEach(box => {
    if (box.value === 'subsidy|yes') box.checked = true;
  });
  render(await request('/api/explore', selected()));
});
