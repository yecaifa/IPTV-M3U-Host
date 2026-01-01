# IPTV Multicast 自动获取与 GitHub 更新

本项目用于 **自动从 iptv.cqshushu.com 搜索 IPTV 源**，  
**筛选 Multicast（组播）类型中有效的 IP**，下载最新的 M3U 文件，并 **自动提交推送到 GitHub**，方便长期订阅使用。

---

## ✨ 功能特性

- 自动搜索指定关键词（如：湖北移动）
- 自动区分 IPTV 类型：
  - ❌ Hotel IPTV（忽略）
  - ✅ Multicast IPTV（仅处理组播）
- 自动识别 IP 状态：
  - ✅ 新上线
  - ✅ 存活 n 天
  - ❌ 暂时失效（自动跳过）
- 支持按 **新 → 旧** 排序，获取 **第 N 新** 的有效组播 IP
- 全流程 **模拟网页点击**（进入详情页 → 查看频道列表 → 下载 M3U）
- 自动更新并推送以下文件到 GitHub：
  - `iptv_latest.m3u`
  - `iptv_m3u_get.py`
  - `运行IPTV脚本.bat`
  - `README.md`
  - `.gitignore`

---

## 📁 项目结构

```text
.
├── iptv_m3u_get.py        # 主脚本（Selenium 自动化）
├── iptv_latest.m3u        # 最新生成的 IPTV M3U 文件
├── 运行IPTV脚本.bat       # Windows 一键运行脚本
├── README.md              # 项目说明
├── .gitignore             # Git 忽略规则
└── .git/                  # Git 仓库目录（不会被上传）
````

---

## ⚙️ 运行环境

* 操作系统：Windows 10 / 11
* Python：3.8 或以上
* 浏览器：Microsoft Edge（Chromium 内核）
* Edge WebDriver（版本需与浏览器一致）

---

## 📦 依赖安装

```bash
pip install selenium gitpython requests
```

> ⚠️ 请确保 `msedgedriver.exe` 已加入系统 PATH，或与脚本放在同一目录。

---

## 🚀 使用方法

### 方法一：双击运行（推荐）

```text
运行IPTV脚本.bat
```

### 方法二：命令行运行

```bash
python iptv_m3u_get.py
```

---

## 🔧 关键配置说明

在 `iptv_m3u_get.py` 中可修改：

```python
SEARCH_KEYWORD = "湖北移动"   # 搜索关键词
TARGET_IP_RANK = 1            # 获取第 N 新的“有效组播 IP”
```

示例说明：

| 配置值                  | 含义       |
| -------------------- | -------- |
| `TARGET_IP_RANK = 1` | 最新可用组播   |
| `TARGET_IP_RANK = 2` | 第二新的可用组播 |
| `TARGET_IP_RANK = 3` | 第三新的可用组播 |

---

## 📡 GitHub 订阅地址

脚本执行成功后，最新 M3U 文件地址为：

```text
https://raw.githubusercontent.com/<你的用户名>/<仓库名>/main/iptv_latest.m3u
```

可直接用于：

* IPTV 播放器
* TVBox
* VLC / Kodi
* 服务器二次分发

---

## ⚠️ 注意事项

* 目标网站页面结构如有调整，可能需要更新 XPath
* 建议定期运行脚本以保持订阅源新鲜
* 本项目仅供 **学习与技术研究用途**
* 请遵守当地法律法规，禁止用于任何商业或非法用途

---

## 📄 License

MIT License
