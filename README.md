# IPTV-M3U-Host

自动从 IPTV 信息网站获取可用频道源，并生成 / 更新 `iptv_latest.m3u`，通过 GitHub Actions 定时运行。

---

## 📡 订阅地址

**Raw（直连）：**  
https://raw.githubusercontent.com/yecaifa/IPTV-M3U-Host/main/iptv_latest.m3u

**Raw 无法直连时（gh-proxy）：**  
https://gh-proxy.com/https://raw.githubusercontent.com/yecaifa/IPTV-M3U-Host/main/iptv_latest.m3u

---

## 🌐 数据来源说明

本项目的数据来源于公开的 IPTV 信息查询网站：

- https://iptv.cqshushu.com

项目通过**模拟浏览器访问**的方式，按网站页面展示结果获取 IPTV 频道列表，用于个人学习与研究用途。

---

## ⚙️ GitHub Actions 使用说明

工作流文件：`.github/workflows/update_m3u.yml`

### 手动运行（推荐）
GitHub → **Actions** → **Update IPTV M3U** → **Run workflow**

可直接填写参数：
- `search_keyword`：搜索关键词（如：湖北省武汉）
- `target_ip_rank`：第几个新的有效组播 IP
- `headless`：是否无头运行（默认 `1`）

无需修改代码或提交。

### 定时运行
默认 **每 6 小时自动运行一次**，使用 workflow 中的默认参数。

---

## 🧪 本地运行（可选）

```powershell
pip install selenium gitpython requests webdriver-manager
$env:SEARCH_KEYWORD="湖北省武汉"
$env:TARGET_IP_RANK="1"
$env:HEADLESS="1"
python iptv_m3u_get_chrome.py
📁 项目结构说明
iptv_m3u_get_chrome.py：主脚本

iptv_latest.m3u：生成的订阅文件

.github/workflows/update_m3u.yml：GitHub Actions 工作流

archive/：历史脚本，仅作留存

⚠️ 免责声明
本项目仅用于个人学习与技术研究，请勿用于商业用途。
使用过程中产生的任何后果由使用者自行承担。

---