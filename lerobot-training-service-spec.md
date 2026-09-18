# LeRobot 訓練服務 — 設計規格

## 1. 系統概觀

讓使用者上傳 LeRobot v3 格式的機器人訓練資料,使用單一固定 RTX 4090 GPU 主機,在 Docker 容器中訓練 ACT 或 SmolVLA policy,完成後下載 checkpoint。

- **目標使用者**:開放給不特定使用者(公開服務)
- **登入**:Hugging Face OAuth,或 Email/密碼註冊登入(擇一),不允許匿名使用

---

## 2. 架構

| 元件 | 技術 | 備註 |
|---|---|---|
| 前端 | React | 部署於 Firebase Hosting |
| 後端 API | FastAPI (Python) | 部署於 Cloud Run |
| 資料庫 | GCP Firestore | 存 job / 使用者 metadata,不存大檔案 |
| 檔案儲存 | GCS | zip 上傳、checkpoint 產出;下載用 signed URL,7 天後過期並刪除 |
| 訓練主機 | 本機 RTX 4090 | 獨立 worker process + Docker 容器 |

### 訓練主機細節
- Worker process:輪詢 Firestore 抓取待處理 job,lock file 確保同時只跑 1 個
- 使用 **Service Account JSON 金鑰檔案**存取 GCP(Firestore / GCS)
- 用 **systemd**(`Restart=always`)管理 worker process,process 意外退出自動重啟
- 每個 policy(ACT / SmolVLA)各自獨立 **Docker image**,訓練在容器內執行,環境互不汙染
- Worker 與訓練容器透過共享 volume 上的 `progress.json` 溝通訓練進度

---

## 3. 使用者流程

1. **登入**(擇一方式):
   - **Hugging Face OAuth**
   - **Email/密碼註冊登入**:
     - 註冊表單加 **reCAPTCHA v3**(前端載入、後端驗證分數),防止腳本量產帳號
     - 此版**不做** email 驗證、**不做**忘記密碼(自助重設)
     - 已登入使用者提供「**修改密碼**」功能(需輸入舊密碼)
   - 兩種登入方式各自建立獨立帳號、獨立計算額度,**此版不支援帳號合併**
2. **提供訓練資料**(擇一):
   - 輸入 Hugging Face Hub dataset repo id(主要方式,只支援**公開**資料集,不處理 private/gated,不儲存使用者 HF token)
   - 上傳 zip 檔(次要方式,前端直接透過 **GCS signed URL** 上傳,不經過後端代理)
3. **上傳確認與驗證**(僅 zip 路徑):
   - 前端上傳成功後呼叫 `confirm-upload` API(失敗自動重試 2 次)
   - 後端非同步、以串流方式讀取 GCS 上的 zip,依序檢查:
     a. LeRobot v3 格式結構是否正確(`meta/info.json`、`data/`、`videos/` 等)
     b. 解壓縮炸彈防護(解壓後總大小上限、單一檔案大小上限、檔案數量上限)
     c. Policy 輸入相容性(讀 meta 裡的 observation/action shape,比對選定 policy 的預期輸入)
   - 全部通過才寫入 Firestore、排入佇列;任一項不通過則標記失敗、清除 GCS 上的物件並附上錯誤訊息
   - HF repo id 路徑改為直接呼叫 HF Hub API 檢查 `meta/info.json` 等檔案是否存在、結構是否正確,不需下載整個資料集
   - 孤兒暫存檔(使用者上傳後未觸發 confirm-upload)由 GCS bucket lifecycle rule 於 **1 天**後自動清除
4. **選擇訓練設定**:
   - Policy:ACT 或 SmolVLA
   - 訓練步數(唯一可調整的超參數,其餘一律使用官方預設值)
5. **佇列與訓練狀態機**:
   - `queued`(排隊中,顯示目前排第幾位)
   - `initializing`(容器已啟動、正在下載/準備資料,尚無 `progress.json`)
   - `training`(容器已寫出第一筆 `progress.json`,顯示目前步數/總步數 + loss)
   - `completed` / `failed` / `cancelled`
   - 「我的 Jobs」頁面以**輪詢**方式顯示狀態;`initializing` 與 `training` 對使用者統一顯示為「準備中 / 訓練中」等簡化文字,不暴露內部子狀態
6. **取消**:`queued`、`initializing`、`training` 任何階段都可取消
   - Firestore 寫入 `cancel_requested` 標記,worker 於下個 heartbeat 週期偵測後 `docker kill` 容器
   - 取消產生的 partial checkpoint **直接丟棄**,不提供下載
7. **完成與下載**:
   - 訓練完成後,打包 checkpoint(policy 權重 + `config.json` + 正規化統計)成 zip
   - 上傳至 GCS(失敗自動重試 2 次,仍失敗則標記為「訓練完成但上傳失敗,請重新送出」,本機 checkpoint 暫不清除以供人工排查)
   - 上傳成功後提供 **GCS signed URL** 下載,同時立即清除本機 checkpoint 檔案
   - 下載連結 **7 天**後過期並自動刪除

---

## 4. 可靠性機制

### Heartbeat 與逾時偵測
- `initializing` 階段:worker 只要確認容器 process 存活即更新 Firestore 上的 heartbeat 時間戳;逾時上限 **5 分鐘**
- `training` 階段:worker 只有在偵測到 `progress.json` 內容(步數/時間戳)有變化時才更新 heartbeat;逾時上限 **2 分鐘**無變化
- **Cloud Scheduler** 每 5 分鐘呼叫一次檢查端點,發現逾時的 job 自動標記為「失敗」,釋放佇列繼續處理下一個

### Worker 重啟與孤兒容器處理
- Firestore 的 job 文件記錄 `container_id`(容器啟動時寫入)
- Worker process(經 systemd)重啟時,執行 `docker ps` 列出本機所有運行中容器,比對 Firestore 中 `initializing` / `training` 狀態 job 的 `container_id`:
  - 對得上 → 重新接手監控(繼續讀 `progress.json`、更新 heartbeat)
  - 對不上(孤兒容器)→ 直接 `docker kill` 清除
- 確保任何時候本機最多只有一個訓練容器占用 GPU

---

## 5. 本機磁碟管理

| 資料類型 | 保留策略 |
|---|---|
| HF Hub 資料集快取 | 保留、LRU 淘汰,總量上限 **20GB**;下載先寫入 `<repo_id>.tmp/` 暫存路徑,完整下載完成才 rename 為正式快取路徑;worker 啟動時清除超過 1 小時的殘留 `.tmp` 資料夾 |
| 使用者上傳 zip(解壓後) | 訓練結束(不論成功 / 失敗 / 取消)即清除,不快取 |
| Checkpoint | 上傳 GCS 成功後立即清除本機檔案;上傳失敗則保留至人工處理完畢 |

---

## 6. 限制與額度

- 資料集大小上限:**2 GB**
- 訓練步數上限:**20,000 步**
- 每人同時進行中(排隊中或訓練中)job 數上限:**1 個**
- 每人每日 job 額度:**10 個**
  - 純排隊中(尚未進入 `initializing`,容器未啟動)取消:**不計額度**
  - 容器已啟動後(`initializing` 或 `training` 階段)取消或失敗:**計入額度**
- 僅支援公開 Hugging Face Hub 資料集,不支援 private / gated 資料集,不儲存使用者 HF token

---

## 7. 已知取捨(供未來參考)

- 訓練步數上限(20,000)與每日額度(10 個)疊加後,單一 RTX 4090 序列排隊情境下,佇列等待時間可能顯著拉長 —— 這是已知且接受的產品體驗取捨,非技術限制。
- Cloud Run 有 32MB 請求主體硬上限,因此大檔案上傳一律採前端直傳 GCS(signed URL)架構,後端不經手檔案本體。
- 目前僅支援公開資料集,是為了避免處理使用者 HF token 儲存的安全性問題;之後如需支援 private/gated 資料集,需重新評估 token 儲存與 OAuth scope 設計。
- Email/密碼註冊此版不做 email 驗證,「每人每日 10 個額度」的防護力因此變弱(reCAPTCHA v3 只能擋腳本量產帳號,擋不住人工手動註冊多個帳號);此為已知且接受的 MVP 範圍取捨,之後若濫用情況明顯,可再補 email 驗證或其他防護。
- 忘記密碼(自助重設)此版不做;使用者若忘記 email/密碼帳號的密碼,目前只能重新註冊新帳號(視為全新使用者,重新起算額度),無法救回原帳號。
