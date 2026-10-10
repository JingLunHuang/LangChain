'use strict';
const $ = id => document.getElementById(id);
const state = { key: '', models: [], pinned: null, busy: false, controller: null };
window.omniEdgeKey = () => state.key;
const taskNames = { general:'一般任務', coding:'程式開發', reasoning:'邏輯推理', writing:'文字寫作', knowledge:'知識檢索' };
const modes = { auto:'自動選模', request:'本次指定', session:'對話固定' };
const examples = [
  ['程式開發','請用 Python 寫一個非同步函式，並除錯可能的例外。'],
  ['邏輯推理','請推導並證明這個數學命題，逐步說明推理。'],
  ['文字潤飾','請把這封 email 改寫成正式的文章，並潤飾語氣。'],
  ['知識檢索','請根據知識庫文件，檢索 KV cache 的設計並引用來源。'],
  ['日常問答','你好，介紹一下這個平台。']
];
function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}
function status(message, error = false) {
  $('status').textContent = message;
  $('status').classList.toggle('error', error);
}
function busy(value) {
  state.busy = value;
  ['preview','connect','disconnect','model','preference','agent','costTier','message','session','review'].forEach(id => $(id).disabled = value);
  $('run').disabled = value || !state.key;
  $('pin').disabled = value || !state.key || !$('session').value;
  $('stop').hidden = !value || !state.controller;
}
async function request(path, body, key = state.key, signal = undefined) {
  const headers = body ? { 'Content-Type':'application/json' } : {};
  if (key) headers['X-API-Key'] = key;
  const response = await fetch(path, { method:body ? 'POST':'GET', headers, body:body ? JSON.stringify(body) : undefined, cache:'no-store', signal });
  if (!response.ok) {
    let message = '無法完成請求，請確認模型設定與平台金鑰。';
    try {
      const payload = await response.json();
      if (typeof payload.detail === 'string') message = payload.detail;
      else if (payload.detail && payload.detail.message) message = payload.detail.message;
      else if (response.status === 422) message = '請確認任務、對話 ID 與選模參數。';
    } catch (_) { /* 保留簡短的可操作錯誤訊息。 */ }
    throw new Error(message);
  }
  return response;
}
function payload() {
  const model = $('model').value;
  const message = $('message').value;
  if (!message.trim()) throw new Error('請先輸入任務。');
  return { message, agent_id:$('agent').value, model_id:model === state.pinned ? null : model, preference:$('preference').value, max_cost_tier:Number($('costTier').value), session_id:$('session').value || null, review:$('review').checked };
}
function showReview(report) {
  $('reviewPanel').hidden = false;
  const labels = { approved:'多個獨立來源一致通過', needs_revision:'多個來源認為仍需修訂', disagreement:'判斷分歧，請自行確認', single_source:'僅一個來源，尚無共識', unavailable:'尚未取得模型評估' };
  $('reviewStatus').textContent = labels[report.status] || report.status;
  $('reviewOpinions').replaceChildren();
  for (const opinion of report.opinions) {
    const row = node('div', 'review-opinion');
    const scores = Object.entries(opinion.scores).map(([axis, value]) => axis + ' ' + Math.round(value * 100) + '%').join(' · ');
    row.append(node('strong', '', opinion.source + ' / ' + opinion.model_id), node('small', '', scores));
    $('reviewOpinions').append(row);
  }
  if (report.revision_accepted) $('reviewOpinions').append(node('small', '', '已自動修訂一次，並由多個來源重新審查通過。'));
  if (report.unavailable_sources.length) $('reviewOpinions').append(node('small', '', '部分評估來源未設定或暫時無法使用。'));
}
async function loadModels() {
  const path = state.key ? '/v1/models?agent_id=' + encodeURIComponent($('agent').value) : '/demo/models';
  const response = await request(path);
  state.models = await response.json();
  $('model').replaceChildren(new Option('自動判別任務並選模', 'auto'));
  for (const model of state.models) {
    const option = new Option(model.label + (model.available ? '' : '（未設定）'), model.id);
    option.disabled = !model.available;
    $('model').append(option);
  }
  if (state.pinned && state.models.some(model => model.id === state.pinned && model.available)) $('model').value = state.pinned;
}
function showDecision(decision) {
  const selected = state.models.find(model => model.id === decision.model_id);
  $('selectedModel').textContent = selected ? selected.label : decision.model_id;
  $('modelDetail').textContent = decision.model_id + ' · ' + decision.provider;
  $('taskFact').textContent = taskNames[decision.task.task] || decision.task.task;
  $('modeFact').textContent = modes[decision.mode] || decision.mode;
  $('budgetFact').textContent = Number(decision.input_budget).toLocaleString();
  $('reasons').replaceChildren(...decision.reasons.map(reason => node('li', '', reason)));
  const scores = decision.candidates.filter(candidate => candidate.eligible).map(candidate => candidate.score);
  const max = Math.max(1, ...scores);
  $('candidates').replaceChildren();
  for (const candidate of decision.candidates) {
    const wrapper = node('div', 'candidate' + (candidate.model_id === decision.model_id ? ' selected' : ''));
    const header = node('div', 'candidate-head');
    header.append(node('span', '', candidate.model_id), node('span', '', candidate.eligible ? candidate.score.toFixed(1) : '未納入'));
    wrapper.append(header);
    if (candidate.eligible) {
      const track = node('div', 'track');
      const bar = node('i');
      bar.style.width = Math.max(4, candidate.score / max * 100) + '%';
      track.append(bar); wrapper.append(track);
    } else wrapper.append(node('small', '', candidate.reason));
    $('candidates').append(wrapper);
  }
  if (decision.session_id) $('session').value = decision.session_id;
}
async function preview() {
  try {
    busy(true); status('正在預覽任務路由…');
    const response = await request(state.key ? '/v1/route' : '/demo/route', payload());
    showDecision(await response.json());
    status(state.key ? '路由預覽完成，可以執行或固定對話模型。' : '離線預覽完成，未呼叫模型。');
  } catch (error) { status(error.message, true); }
  finally { busy(false); }
}
async function connect() {
  const key = $('apiKey').value.trim();
  if (!key) { status('請輸入平台 API Key；離線預覽無需金鑰。', true); return; }
  try {
    busy(true);
    const response = await request('/v1/agents', undefined, key);
    const agents = await response.json();
    if (!agents.length) throw new Error('此金鑰沒有可用的 Agent。');
    const previous = $('agent').value;
    const names = { chat:'一般任務', default:'知識檢索' };
    $('agent').replaceChildren(...agents.map(agent => new Option(names[agent.id] || agent.description || agent.id, agent.id)));
    if (agents.some(agent => agent.id === previous)) $('agent').value = previous;
    state.key = key; state.pinned = null; $('session').value = '';
    await loadModels();
    $('apiKey').value = '';
    $('modeBadge').textContent = '平台已連線'; $('modeBadge').classList.add('connected');
    $('disconnect').hidden = false;
    status('平台已連線。先預覽，再執行你選擇的模型。');
  } catch (error) { state.key = ''; status(error.message, true); }
  finally { busy(false); }
}
async function disconnect() {
  state.key = ''; state.pinned = null; $('apiKey').value = ''; $('session').value = '';
  $('modeBadge').textContent = '離線預覽'; $('modeBadge').classList.remove('connected'); $('disconnect').hidden = true;
  $('agent').replaceChildren(new Option('一般任務','chat'), new Option('知識檢索','default'));
  await loadModels(); busy(false); status('已斷開平台，回到離線預覽。');
}
async function pin() {
  try {
    busy(true);
    const model = $('model').value === 'auto' ? null : $('model').value;
    const response = await request('/v1/sessions/model', { session_id:$('session').value, agent_id:$('agent').value, model_id:model, preference:$('preference').value, max_cost_tier:Number($('costTier').value) });
    const result = await response.json(); state.pinned = result.model_id;
    status(result.model_id ? '此對話已固定模型，原有歷史會保留。' : '此對話已恢復自動選模，原有歷史會保留。');
  } catch (error) { status(error.message, true); }
  finally { busy(false); }
}
async function run() {
  if (!state.key) return;
  state.controller = new AbortController(); busy(true); $('output').textContent = ''; $('reviewPanel').hidden = true;
  status('正在執行 Agent…'); let completed = false;
  try {
    if ($('review').checked) {
      status('正在產生回答並收集獨立評估…');
      const response = await request('/v1/invoke', payload(), state.key, state.controller.signal);
      const result = await response.json();
      $('session').value = result.session_id; showDecision(result.route);
      $('output').textContent = result.output;
      showReview(result.review);
      status('回答與評估完成；評估不能保證事實正確。');
      return;
    }
    const response = await request('/v1/stream', payload(), state.key, state.controller.signal);
    const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = '';
    function frame(text) {
      let event = 'message'; const data = [];
      for (const line of text.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim();
        if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
      }
      const value = data.join('\n'); if (!value) return;
      if (value === '[DONE]') { completed = true; return; }
      const content = JSON.parse(value);
      if (event === 'error') throw new Error('Agent 執行失敗，請確認供應商與工具設定。');
      if (event === 'session') $('session').value = content.session_id;
      else if (event === 'route') showDecision(content);
      else if (typeof content.delta === 'string') $('output').textContent += content.delta;
    }
    while (true) {
      const chunk = await reader.read();
      buffer += decoder.decode(chunk.value || new Uint8Array(), { stream:!chunk.done });
      let boundary;
      while ((boundary = buffer.indexOf('\n\n')) >= 0) { frame(buffer.slice(0,boundary)); buffer = buffer.slice(boundary + 2); }
      if (chunk.done) break;
    }
    if (!completed) throw new Error('串流未完整結束，可檢查平台的路由紀錄。');
    status('執行完成。你可以切換模型繼續同一段對話。');
  } catch (error) { status(error.name === 'AbortError' ? '已停止本次串流。' : error.message, error.name !== 'AbortError'); }
  finally { state.controller = null; busy(false); }
}
for (const [label, message] of examples) {
  const button = node('button', 'chip', label);
  button.addEventListener('click', () => { if (!state.busy) { $('message').value = message; preview(); } });
  $('samples').append(button);
}
$('preview').addEventListener('click', preview); $('connect').addEventListener('click', connect);
$('disconnect').addEventListener('click', () => disconnect().catch(error => status(error.message, true)));
$('run').addEventListener('click', run); $('pin').addEventListener('click', pin);
$('stop').addEventListener('click', () => state.controller && state.controller.abort());
$('agent').addEventListener('change', async () => {
  busy(true); state.pinned = null; $('session').value = '';
  try { await loadModels(); status('Agent 已切換，請重新預覽路由。'); }
  catch (error) { status(error.message, true); }
  finally { busy(false); }
});
$('session').addEventListener('change', () => { state.pinned = null; busy(false); });
loadModels().then(preview).catch(error => status(error.message, true));
