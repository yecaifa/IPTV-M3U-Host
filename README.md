# IPTV-M3U-Host

自动抓取 IPTV 频道列表并更新 `iptv_latest.m3u`（GitHub Actions 定时运行）。

## 订阅地址

**Raw：**
https://raw.githubusercontent.com/yecaifa/IPTV-M3U-Host/main/iptv_latest.m3u

**Raw 无法直连时（gh-proxy）：**
https://gh-proxy.com/https://raw.githubusercontent.com/yecaifa/IPTV-M3U-Host/main/iptv_latest.m3u

## GitHub Actions

工作流：`.github/workflows/update_m3u.yml`

可在 workflow 中修改：
- `SEARCH_KEYWORD`
- `TARGET_IP_RANK`

## 本地运行（可选）

```powershell
pip install selenium gitpython requests webdriver-manager
$env:SEARCH_KEYWORD="湖北省武汉"
$env:TARGET_IP_RANK="1"
$env:HEADLESS="1"
python iptv_m3u_get_chrome.py
