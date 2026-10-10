# Edge Reasoner：OmniRoute 擴充模組

原有 OmniRoute Studio 首頁、選模、路由、串流回應及多模型審查保持原樣。首頁工作區下方新增可展開的 Edge Reasoner 區塊，沿用同一把平台 API Key 與相同租戶鑑權。展開後可查看真實資料狀態、上傳儀表圖片、執行本地推理及選擇雲端備援。原平台 API、CLI、MCP 保持可用。

## 本機啟動

在本目錄執行原有的 `scripts/start-demo.ps1 -Port 8000`，於 `http://127.0.0.1:8000/` 開啟原平台 UI。既有示範金鑰保存在 `.state/demo-key.json`，不要提交。連接金鑰後展開 Edge Reasoner。若要實際執行本地推理，需先啟動 Ollama 並備妥 `OLLAMA_TEXT_MODEL` 指定的模型；預設為 `edge-reasoner`。如尚未完成微調，可設成已安裝的本地基座模型測試接線。圖片推理另需設定 `OLLAMA_VISION_MODEL`；未設定時回傳 `vision_model_not_configured`，不會假稱已理解圖片。勾選雲端備援前需在伺服器環境設定 `DASHSCOPE_API_KEY`。

同一組鑑權 API：`GET /v1/edge/status`、`GET /v1/edge/evaluation`、`POST /v1/edge/run`。執行要求 JSON 為 `question`、選填 `image_base64`、`allow_cloud_fallback`。圖片限制 10 MB。當沒有實測評估時 evaluation 回傳 404，UI 明確顯示尚未產生。

## 資料與訓練流程

`data/seed_questions.json` 為 12 題示範種子，`data/grpo_prompts.jsonl` 為 6 題探索題，`data/eval_cases.json` 為 3 題留出題。兩張課程儀表圖片和 `data/vl_labels.json` 可供小樣本視覺流程驗證；其中第二張原始 Excel 將 56.6 miles 小計里程誤列為速度，已按圖片改成速度 0。這些數量只足以驗證接線，不能代表模型泛化或訓練成果。`data/preference.md` 是示範偏好，正式使用前需確認。

訓練依賴請在獨立的 Linux/CUDA 環境安裝 `requirements-edge-train.txt`。腳本採用原先的順序；所有雲端產生的 SFT 與第二輪 RST 候選預設未審核，必須人工檢查後才可進入訓練：

```bash
python scripts/01_qwen_max_distiller.py
python scripts/01_qwen_max_distiller.py --execute --limit 6
python scripts/03_vl_perception_module.py
python scripts/02_sft_knowledge_injection.py --train
python scripts/03_vl_perception_module.py --train --allow-demo-two
python scripts/04_grpo_co_work_pipeline.py train --judge-budget 120
python scripts/04_grpo_co_work_pipeline.py sample --judge-budget 24
python scripts/04_grpo_co_work_pipeline.py select
python scripts/02_sft_knowledge_injection.py --dataset data/sft_round2.jsonl --base-model models/grpo_model_7b --output models/final_co_work_model_7b --train
python scripts/05_eval_and_agent.py --generate --model base=Qwen/Qwen2.5-7B-Instruct --model sft=models/sft_model_7b --model co_work=models/final_co_work_model_7b
python scripts/05_eval_and_agent.py --responses outputs/eval_responses.jsonl --judge --chart
python scripts/06_gguf_export.py --export
```

以上是執行順序，不表示已訓練或已取得評估數字。要進行正式模型比較，需擴大資料量、盲評、重複執行、記錄 token 與費用、同負載比較並報告不確定性。`<thinking>` 欄位是簡短、可核對的公開依據摘要，不表示可讀取模型內部思維。保單或理賠案例必須依正式條款與人工審核。

## 端到端回測

先在本機啟動原平台，設定已安裝的 `OLLAMA_TEXT_MODEL`，再執行 `python scripts/07_backtest.py --repeats 2`。腳本會先確認原平台健康、原有離線預覽與 Edge API 鑑權，核對訓練種子與留出題沒有完全重複，然後逐題實際呼叫 Agent。原始輸出寫入 `outputs/backtest_responses.jsonl`，摘要寫入 `outputs/backtest.json`，在原 UI 的 Agent 回測區塊可以查看。這兩個執行產物不會提交。

自動檢查只涵蓋 HTTP 成功、XML 格式、明確禁止用語、本地/雲端呼叫紀錄；事實正確性必須逐題人工核對。將覆核結論寫成 `{"eval-01#1": {"pass": true, "note": "依據..."}}` 等格式的 JSON，再執行 `python scripts/07_backtest.py --replay --review-file <路徑>`，會用保存的實際回應重算報告，不重跑模型。`passed_small_sample` 僅代表此小樣本及這次設定下通過；若缺 SFT/Co-work 權重或 Qwen-Max API，三模型 A/B、教師分數與成本比保持空值。

## 2026-10-10 實際回測紀錄

原平台以 `OLLAMA_TEXT_MODEL=qwen2.5-coder:7b` 執行 `python scripts/07_backtest.py --repeats 2`，對 3 道留出題共呼叫 6 次。自動檢查 6/6 通過；逐次人工核對事實後 4/6 通過、2/6 失敗，失敗均為互相矛盾且缺生效日期的保單節錄未要求正式有效版本與人工確認。平均延遲 9.710 秒；原始回應、人工註記和報告保存在本機忽略追蹤的 `outputs/backtest_responses.jsonl`、`outputs/backtest_review.json`、`outputs/backtest.json`。

另以 `python scripts/05_eval_and_agent.py --generate --model base=ollama:qwen2.5-coder:7b` 直接測 3 道留出題，XML 格式通過率 0/3，平均輸出速度 10.637 tokens/s。這是未微調基座模型的觀測值，`outputs/evaluation.json` 會明確列出缺少 `sft` 與 `co_work`。沒有教師金鑰、SFT/GRPO 權重或視覺模型，因此教師評分、三模型比較、成本節省率及實際 VL 準確率都未產生。無視覺模型時上傳圖片已驗證回傳 `needs_review` 與 `vision_model_not_configured`，不會宣稱看懂圖片。