# IPTV-M3U-Host

自动从公开 IPTV 信息网站获取可用频道源，并生成 / 更新 M3U 文件。  
项目通过 **GitHub Actions** 定时运行，无需本地服务器。

---

## 📡 订阅地址

### 单文件（最近一次单次模式的输出）
**Raw（直连）：**  
https://raw.githubusercontent.com/yecaifa/IPTV-M3U-Host/main/iptv_latest.m3u

**Raw 无法直连时（gh-proxy）：**  
https://gh-proxy.com/https://raw.githubusercontent.com/yecaifa/IPTV-M3U-Host/main/iptv_latest.m3u

### 多文件（每省一个文件）
批量模式输出在仓库目录：`m3u/`  
例如（以湖北为例）：

- https://raw.githubusercontent.com/yecaifa/IPTV-M3U-Host/main/m3u/湖北.m3u
- https://gh-proxy.com/https://raw.githubusercontent.com/yecaifa/IPTV-M3U-Host/main/m3u/湖北.m3u

---

## 🌐 数据来源

本项目使用以下公开 IPTV 信息查询网站作为数据来源：

- https://iptv.cqshushu.com

通过模拟浏览器访问页面并按展示结果生成频道列表，仅用于个人学习与技术研究。

---

## ⚙️ GitHub Actions 使用说明

工作流文件：`.github/workflows/update_m3u.yml`

GitHub → **Actions** → **Update IPTV M3U** → **Run workflow**

可填写参数：
- `mode`：`single`（更新 `iptv_latest.m3u`）或 `batch`（每省生成 `m3u/<省>.m3u`）
- `search_keyword`：单次模式关键词（`mode=single` 时生效）
- `target_ip_rank`：第几个新的有效组播 IP
- `keyword_template`：批量模式关键词模板（`mode=batch` 时生效），使用 `{province}` 占位  
  - 例：`{province}`、`{province}省`
- `headless`：是否无头运行（默认 `1`）

---

## 🧪 本地运行（可选）

### 单次模式
```powershell
pip install selenium requests webdriver-manager
$env:SEARCH_KEYWORD="湖北省武汉"
$env:TARGET_IP_RANK="1"
$env:HEADLESS="1"
python iptv_m3u_get_chrome.py
```
### 批量模式（每省一个文件）
```powershell
pip install selenium requests webdriver-manager
$env:BATCH="1"
$env:KEYWORD_TEMPLATE="{province}"   # 也可以用 "{province}省"
$env:TARGET_IP_RANK="1"
$env:HEADLESS="1"
python iptv_m3u_get_chrome.py
```
---

## 📁 项目结构说明

- `iptv_m3u_get_chrome.py`：主脚本
- `iptv_latest.m3u`：单次模式输出
- `m3u/`：批量模式输出（每省一个文件）
- `.github/workflows/update_m3u.yml`：GitHub Actions 工作流
- `archive/`：历史脚本，仅作留存

---

## ⚠️ 免责声明

本项目仅用于个人学习与技术研究，请勿用于商业用途。  
使用过程中产生的任何后果由使用者自行承担。

---