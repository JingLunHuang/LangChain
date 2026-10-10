'use strict';
(() => {
  const get = id => document.getElementById(id);
  const key = () => window.omniEdgeKey ? window.omniEdgeKey() : '';
  const message = (value, error = false) => {
    get('edgeMessage').textContent = value;
    get('edgeMessage').classList.toggle('error', error);
  };
  async function request(path, body) {
    if (!key()) throw new Error('請先在上方連接平台 API Key。');
    const headers = {'X-API-Key': key()};
    if (body) headers['Content-Type'] = 'application/json';
    const response = await fetch(path, {method:body ? 'POST' : 'GET', headers,
      body:body ? JSON.stringify(body) : undefined, cache:'no-store'});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `HTTP ${response.status}`);
    return data;
  }
  function fact(label, value) {
    const box = document.createElement('div'); box.className = 'edge-fact';
    const title = document.createElement('span'); title.textContent = label;
    const number = document.createElement('strong'); number.textContent = String(value);
    box.append(title, number); return box;
  }
  async function refresh() {
    try {
      const status = await request('/v1/edge/status');
      get('edgeFacts').replaceChildren(
        fact('種子題', status.seed_questions), fact('已審核 SFT 筆數', status.reviewed_sft_examples),
        fact('GRPO 題目', status.grpo_prompts), fact('已觀測 rollout', status.observed_rollouts),
        fact('SFT 模型', status.models.sft ? '已存在' : '未產生'),
        fact('最終協同模型', status.models.final ? '已存在' : '未產生'),
        fact('Qwen-Max 金鑰', status.teacher_key_configured ? '已設定' : '未設定'),
        fact('評估報告', status.evaluation_available ? '已產生' : '未產生'),
        fact('Agent 回測', status.backtest_available ? status.backtest_overall : '未產生'));
      try {
        const report = await request('/v1/edge/evaluation');
        get('edgeEvaluation').textContent = JSON.stringify(report, null, 2);
      } catch (error) {
        get('edgeEvaluation').textContent = error.message === 'No observed evaluation is available'
          ? '目前沒有已產生的評估報告。' : error.message;
      }
      try {
        const report = await request('/v1/edge/backtest');
        get('edgeBacktest').textContent = JSON.stringify({overall:report.overall,
          n_cases:report.n_cases, repeats:report.repeats, n_runs:report.n_runs,
          auto_pass_runs:report.auto_pass_runs, human_pass_runs:report.human_pass_runs,
          latency_seconds:report.latency_seconds, model_matrix:report.model_matrix,
          limits:report.limits}, null, 2);
      } catch (error) {
        get('edgeBacktest').textContent = error.message === 'No observed backtest is available'
          ? '目前沒有已產生的回測報告。' : error.message;
      }
      message('已更新實際狀態。');
    } catch (error) { message(error.message, true); }
  }
  function imageBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(',', 2)[1]);
      reader.onerror = () => reject(new Error('無法讀取圖片。'));
      reader.readAsDataURL(file);
    });
  }
  async function run() {
    const question = get('edgeQuestion').value.trim();
    const image = get('edgeImage').files[0];
    if (!question) { message('請輸入問題。', true); return; }
    if (image && (image.size > 10 * 1024 * 1024 || !['image/png','image/jpeg','image/webp'].includes(image.type))) {
      message('僅接受 10 MB 以下的 PNG、JPEG 或 WebP 圖片。', true); return;
    }
    get('edgeRun').disabled = true; message('正在執行本地推理…');
    try {
      const result = await request('/v1/edge/run', {question,
        image_base64:image ? await imageBase64(image) : null,
        allow_cloud_fallback:get('edgeCloud').checked});
      get('edgeAnswer').textContent = result.answer || result.response;
      get('edgeTrace').textContent = JSON.stringify({route:result.route, reason_summary:result.reason_summary,
        perception:result.perception, sources:result.sources,
        local_calls:result.local_calls, cloud_calls:result.cloud_calls}, null, 2);
      message(result.route === 'needs_review' ? '已完成；輸出需要人工檢查。' : '已完成。');
    } catch (error) { message(error.message, true); }
    finally { get('edgeRun').disabled = false; }
  }
  get('edgePanel').addEventListener('toggle', () => { if (get('edgePanel').open) refresh(); });
  get('edgeRefresh').addEventListener('click', refresh);
  get('edgeRun').addEventListener('click', run);
})();
