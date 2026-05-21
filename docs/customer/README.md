# VibeVoice Client

VibeVoice 語音辨識客戶端部署包。

- **離線轉錄**：上傳音/影檔（≤ 1GB、≤ 61 分鐘） → 中文/英文/混合語音辨識
- **WebSocket API**：即時推送 segment 結果
- **Hotwords**：per-request + 持久化群組
- **GPU 部署**：NVIDIA Ampere+，docker compose 一鍵起

詳細安裝請見 [INSTALL.md](INSTALL.md)。

## 快速開始

    ./scripts/clone_upstream.sh
    cp config/api_keys.example.yaml config/api_keys.yaml
    nano config/api_keys.yaml
    cp .env.example .env
    ./scripts/preflight.sh
    docker compose up -d --build
    ./scripts/wait_for_ready.sh
    ./scripts/smoke_test.sh

## License

(待定)
