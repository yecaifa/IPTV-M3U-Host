# -*- coding: utf-8 -*-
"""
iptv_m3u_get_chrome.py
- Chrome + Selenium（兼容本地/CI）
- 支持运行时输入 / 环境变量配置：SEARCH_KEYWORD, TARGET_IP_RANK
- Headless 兼容增强（更像真实浏览器 + 显式等待动态内容）
- 保持“模拟点击”流程：进入IP详情页 -> 查看频道列表 -> M3U下载
- Git 仅提交 iptv_latest.m3u
"""

import os
import re
import time
import urllib.parse
from typing import Optional, Tuple

from git import Repo
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By


# ===================== 默认配置（可被环境变量/输入覆盖）=====================
DEFAULT_SEARCH_KEYWORD = "湖北省武汉"
DEFAULT_TARGET_IP_RANK = 1  # 获取“有效组播IP”里的第n新（1=最新）

HOME_PAGE_URL = "https://iptv.cqshushu.com"
ELEMENT_TIMEOUT = 60
PAGE_LOAD_TIMEOUT = 120
FIXED_DELAY = 3

# 是否在 m3u 顶部写入本次来源标记（保证换rank/换IP后一定产生diff）
ENABLE_STAMP = True

# GitHub配置
GITHUB_REPO_PATH = os.path.dirname(os.path.abspath(__file__))
GITHUB_M3U_FILE_NAME = "iptv_latest.m3u"
GITHUB_BRANCH = "main"
YOUR_GITHUB_USERNAME = "yecaifa"

M3U_PATH = os.path.join(GITHUB_REPO_PATH, GITHUB_M3U_FILE_NAME)
# ============================================================================


def get_runtime_config() -> Tuple[str, int]:
    """
    优先级：
      1) 环境变量 SEARCH_KEYWORD / TARGET_IP_RANK
      2) 本地交互输入（仅在 TTY 且无环境变量时）
      3) 默认值
    """
    kw_env = (os.getenv("SEARCH_KEYWORD") or "").strip()
    rk_env = (os.getenv("TARGET_IP_RANK") or "").strip()

    keyword = kw_env if kw_env else DEFAULT_SEARCH_KEYWORD
    rank = DEFAULT_TARGET_IP_RANK
    if rk_env.isdigit():
        rank = int(rk_env)

    # 本地交互（Actions/CI 通常没有 stdin）
    try:
        is_tty = os.isatty(0)
    except Exception:
        is_tty = False

    if is_tty and (not kw_env and not rk_env):
        kw_in = input(f"请输入搜索关键词（回车=默认：{DEFAULT_SEARCH_KEYWORD}）：").strip()
        rk_in = input(f"请输入第几个新的IP（回车=默认：{DEFAULT_TARGET_IP_RANK}）：").strip()

        if kw_in:
            keyword = kw_in
        if rk_in.isdigit():
            rank = int(rk_in)

    if rank < 1:
        rank = 1
    return keyword, rank


def upload_m3u_to_github(target_ip_rank: int) -> str:
    """仅上传/更新 M3U 文件到GitHub（只提交 iptv_latest.m3u）"""
    try:
        if not os.path.exists(GITHUB_REPO_PATH) or not os.path.exists(os.path.join(GITHUB_REPO_PATH, ".git")):
            raise Exception("当前目录不是Git仓库（缺少.git）")
        if not os.path.exists(M3U_PATH) or os.path.getsize(M3U_PATH) == 0:
            raise Exception("M3U文件不存在或为空，无法提交")

        repo = Repo(GITHUB_REPO_PATH)
        git = repo.git

        if "origin" not in [r.name for r in repo.remotes]:
            raise Exception("未配置远程 origin，请先设置远程仓库")

        git.add(GITHUB_M3U_FILE_NAME)

        # HEAD 不存在（首次提交）兜底
        if not repo.head.is_valid():
            commit_msg = f"Update M3U - {time.strftime('%Y-%m-%d %H:%M:%S')}"
            git.commit("-m", commit_msg)
            git.push("origin", GITHUB_BRANCH)
            print(f"✅ GitHub上传成功：{commit_msg}")
            return f"https://raw.githubusercontent.com/{YOUR_GITHUB_USERNAME}/IPTV-M3U-Host/{GITHUB_BRANCH}/{GITHUB_M3U_FILE_NAME}"

        # staged diff 判断该文件是否变化
        changed = repo.index.diff("HEAD")
        changed_files = {d.a_path for d in changed}

        if GITHUB_M3U_FILE_NAME in changed_files:
            commit_msg = f"Update M3U (有效组播第{target_ip_rank}新IP) - {time.strftime('%Y-%m-%d %H:%M:%S')}"
            git.commit("-m", commit_msg)
            git.push("origin", GITHUB_BRANCH)
            print(f"✅ GitHub上传成功：{commit_msg}")
        else:
            print("ℹ️ M3U 文件无变化，无需提交")

        return f"https://raw.githubusercontent.com/{YOUR_GITHUB_USERNAME}/IPTV-M3U-Host/{GITHUB_BRANCH}/{GITHUB_M3U_FILE_NAME}"

    except Exception as e:
        raise Exception(f"GitHub上传失败：{str(e)}")


def make_driver(download_dir: str) -> webdriver.Chrome:
    """
    创建 Chrome WebDriver（跨平台）
    - Windows：显式指定 chrome.exe（避免 chrome 不在 PATH）
    - Linux/CI：不指定 binary_location，使用 PATH 中的 chrome（workflow 已安装）
    """
    import platform
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    headless_env = (os.getenv("HEADLESS") or "1").strip()
    headless = headless_env not in ("0", "false", "False")

    options = ChromeOptions()

    # 仅 Windows 显式指定 Chrome 路径
    if platform.system().lower() == "windows":
        chrome_path = os.path.join(
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            r"Google\Chrome\Application\chrome.exe"
        )
        if not os.path.exists(chrome_path):
            candidates = [
                os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                             r"Google\Chrome\Application\chrome.exe"),
                os.path.join(os.environ.get("LOCALAPPDATA", ""),
                             r"Google\Chrome\Application\chrome.exe"),
            ]
            chrome_path = next((p for p in candidates if p and os.path.exists(p)), None)

        if not chrome_path or not os.path.exists(chrome_path):
            raise Exception("未找到 chrome.exe：请确认已安装 Chrome")

        options.binary_location = chrome_path

    if headless:
        options.add_argument("--headless=new")

    # 基本稳定性参数
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    # Headless / 自动化兼容增强
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    # 下载目录设置
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    options.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    # 去掉 webdriver 标记
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        })
    except Exception:
        pass

    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    driver.set_script_timeout(ELEMENT_TIMEOUT)
    return driver


def wait_for_new_m3u_file(download_dir: str, before_snapshot: dict, click_time: float, timeout_sec: int = 180) -> Optional[str]:
    """
    等待“新下载”的 m3u：
    - 优先：出现一个 before_snapshot 中不存在的新文件
    - 次优：已有 m3u 文件的 mtime 变得比 click_time 更新
    """
    deadline = time.time() + timeout_sec

    def list_m3u():
        files = []
        for f in os.listdir(download_dir):
            if f.lower().endswith(".m3u"):
                full = os.path.join(download_dir, f)
                try:
                    files.append((f, os.path.getmtime(full), os.path.getsize(full), full))
                except Exception:
                    continue
        return files

    while time.time() < deadline:
        m3us = list_m3u()

        # 1) 新文件（之前不存在）
        new_files = [x for x in m3us if x[0] not in before_snapshot and x[2] > 0]
        if new_files:
            new_files.sort(key=lambda x: x[1], reverse=True)
            return new_files[0][3]

        # 2) 老文件被更新（mtime 变新）
        updated_files = []
        for name, mtime, size, full in m3us:
            if size <= 0:
                continue
            old_mtime = before_snapshot.get(name)
            if old_mtime is not None and mtime > old_mtime + 0.5:
                updated_files.append((name, mtime, full))
            elif mtime > click_time + 0.5:
                updated_files.append((name, mtime, full))

        if updated_files:
            updated_files.sort(key=lambda x: x[1], reverse=True)
            return updated_files[0][2]

        time.sleep(1)

    return None

def wait_for_dynamic_content(driver: webdriver.Chrome, timeout_sec: int = 25):
    """等待动态内容出现（headless 下非常关键）"""
    try:
        WebDriverWait(driver, timeout_sec).until(
            EC.presence_of_element_located(
                (By.XPATH, "//*[contains(., 'Multicast IPTV') or contains(., '组播')]")
            )
        )
    except Exception:
        pass


def stamp_m3u(target_ip: str, target_ip_rank: int):
    """在 m3u 头部写入本次来源标记（不影响播放器）"""
    if not ENABLE_STAMP:
        return
    try:
        stamp = f"# source_ip={target_ip} rank={target_ip_rank} updated_at={time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        with open(M3U_PATH, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        lines = content.splitlines(True)
        # 移除旧 stamp
        lines = [ln for ln in lines if not ln.startswith("# source_ip=")]

        if lines and lines[0].startswith("#EXTM3U"):
            lines.insert(1, stamp)
        else:
            lines.insert(0, stamp)

        with open(M3U_PATH, "w", encoding="utf-8") as f:
            f.write("".join(lines))
    except Exception:
        pass


def extract_m3u(search_keyword: str, target_ip_rank: int):
    print(f"【路径验证】仓库目录：{GITHUB_REPO_PATH}")
    print(f"【路径验证】M3U文件路径：{M3U_PATH}")
    print(f"【路径验证】是否为Git仓库：{os.path.exists(os.path.join(GITHUB_REPO_PATH, '.git'))}")
    print(f"【当前配置】关键词={search_keyword}，第{target_ip_rank}新IP")

    driver = None
    github_link = None

    try:
        driver = make_driver(download_dir=GITHUB_REPO_PATH)

        # 1) 打开首页
        print(f"【步骤1】打开首页：{HOME_PAGE_URL}")
        driver.get(HOME_PAGE_URL)
        time.sleep(FIXED_DELAY * 2)

        # 2) 搜索关键词
        print(f"【步骤2】搜索：{search_keyword}")
        try:
            search_input = driver.find_element(By.NAME, "q")
            search_input.clear()
            search_input.send_keys(search_keyword)
            search_input.submit()
        except Exception:
            encoded_key = urllib.parse.quote(search_keyword)
            driver.get(f"{HOME_PAGE_URL}?q={encoded_key}")

        time.sleep(FIXED_DELAY * 2)
        wait_for_dynamic_content(driver, timeout_sec=25)

        # 3) 只提取 Multicast IPTV 中“有效”的组播IP
        print(f"【步骤3】提取 Multicast IPTV 中有效的组播IP...")

        ip_pattern_anywhere = re.compile(r'(\d{1,3}(?:\.\d{1,3}){3})')
        alive_days_pattern = re.compile(r'存活\s*(\d+)\s*天')

        def parse_status(text: str):
            t = text.replace("\u3000", " ").strip()
            if "暂时失效" in t:
                return (False, (99, 999999), "暂时失效")
            if "新上线" in t:
                return (True, (0, 0), "新上线")
            m = alive_days_pattern.search(t)
            if m:
                days = int(m.group(1))
                return (True, (1, days), f"存活{days}天")
            return (False, (99, 999999), t)

        multicast_root = None
        try:
            multicast_title = driver.find_element(
                By.XPATH,
                "//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'multicast iptv')]"
            )
            multicast_root = multicast_title.find_element(
                By.XPATH,
                "ancestor::*[self::div or self::section or self::main or self::body][1]"
            )
        except Exception:
            multicast_root = None

        if multicast_root:
            candidate_rows = multicast_root.find_elements(By.XPATH, ".//tr | .//li | .//div")
        else:
            candidate_rows = driver.find_elements(By.XPATH, "//*[self::tr or self::li or self::div][contains(., '组播')]")

        multicast_items = []
        seen_ip = set()

        for row in candidate_rows:
            try:
                row_text = row.text.strip()
                if not row_text:
                    continue
                if "组播" not in row_text:
                    continue

                m_ip = ip_pattern_anywhere.search(row_text)
                if not m_ip:
                    continue
                ip = m_ip.group(1)

                if ip in seen_ip:
                    continue

                link_elem = None
                try:
                    link_elem = row.find_element(By.XPATH, f".//a[normalize-space(text())='{ip}']")
                except Exception:
                    try:
                        link_elem = row.find_element(By.XPATH, f".//a[contains(normalize-space(.), '{ip}')]")
                    except Exception:
                        link_elem = None

                if not link_elem:
                    continue

                is_valid, sort_key, status_norm = parse_status(row_text)
                if not is_valid:
                    continue

                seen_ip.add(ip)
                multicast_items.append({
                    "ip": ip,
                    "link": link_elem,
                    "status": status_norm,
                    "sort_key": sort_key
                })
            except Exception:
                continue

        print(f"  ✅ 提取到 {len(multicast_items)} 个有效组播IP")
        if not multicast_items:
            print("❌ 未找到任何有效的组播IP，流程终止")
            return

        multicast_items.sort(key=lambda x: x["sort_key"])

        print("  📋 有效组播IP列表（1=最新）：")
        for idx, item in enumerate(multicast_items, start=1):
            mark = "【选中】" if idx == target_ip_rank else ""
            print(f"    第{idx}名：{item['ip']}  状态：{item['status']} {mark}")

        if target_ip_rank < 1 or target_ip_rank > len(multicast_items):
            raise Exception(f"目标IP排名超出范围（有效组播IP数量：{len(multicast_items)}，目标排名：{target_ip_rank}）")

        target = multicast_items[target_ip_rank - 1]
        target_ip = target["ip"]
        target_link = target["link"]
        print(f"  ✅ 选中第 {target_ip_rank} 新的有效组播IP：{target_ip}（{target['status']}）")

        # 4) 进入 IP 详情页（模拟点击）
        print(f"【步骤4】进入IP详情页：{target_ip}")
        target_link.click()
        WebDriverWait(driver, ELEMENT_TIMEOUT).until(EC.staleness_of(target_link))
        time.sleep(FIXED_DELAY * 2)

        # 5) 点击“查看频道列表”
        print("【步骤5】点击查看频道列表")
        channel_btn = WebDriverWait(driver, ELEMENT_TIMEOUT).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), '查看频道列表')]"))
        )
        channel_btn.click()

        driver.switch_to.window(driver.window_handles[-1])
        time.sleep(FIXED_DELAY * 2)

        # 6) 点击“M3U下载”
        print("【步骤6】点击M3U下载")
        m3u_download_btn = WebDriverWait(driver, ELEMENT_TIMEOUT).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'M3U下载')]"))
        )
        m3u_download_btn.click()

        # 7) 等待“新下载”的 m3u 出现（关键：不要误用旧的 iptv_latest.m3u）
        print("【步骤7】等待下载完成")

        # 点击前先快照目录中现有的 m3u 文件（避免把旧文件当新文件）
        before_snapshot = {}
        for f in os.listdir(GITHUB_REPO_PATH):
            if f.lower().endswith(".m3u"):
                full = os.path.join(GITHUB_REPO_PATH, f)
                try:
                    before_snapshot[f] = os.path.getmtime(full)
                except Exception:
                    pass

        click_time = time.time()
        time.sleep(1)  # 给下载触发一点时间

        downloaded = wait_for_new_m3u_file(GITHUB_REPO_PATH, before_snapshot, click_time, timeout_sec=180)
        if not downloaded or not os.path.exists(downloaded) or os.path.getsize(downloaded) == 0:
            raise Exception("M3U文件下载失败（未检测到新的 .m3u 文件）")

        # 用“新下载”的文件覆盖到 iptv_latest.m3u
        if os.path.abspath(downloaded) != os.path.abspath(M3U_PATH):
            os.replace(downloaded, M3U_PATH)

        if not os.path.exists(M3U_PATH) or os.path.getsize(M3U_PATH) == 0:
            raise Exception("M3U文件下载失败（文件为空或不存在）")


        # 写入来源标记（确保换rank/换IP有diff）
        stamp_m3u(target_ip, target_ip_rank)

        print(f"✅ M3U源文件已下载：{M3U_PATH}")

        # 8) 上传到 GitHub（只提交 m3u）
        print("【步骤8】上传到GitHub（仅m3u）")
        do_push = (os.getenv("DO_PUSH") or "0").strip() in ("1", "true", "True")

        if do_push:
            print("【步骤8】上传到GitHub（脚本内push）")
            github_link = upload_m3u_to_github(target_ip_rank)
        else:
            print("【步骤8】跳过脚本内push（由GitHub Actions负责提交）")
            github_link = f"https://raw.githubusercontent.com/{YOUR_GITHUB_USERNAME}/IPTV-M3U-Host/{GITHUB_BRANCH}/{GITHUB_M3U_FILE_NAME}"


        print("\n【完成】=====")
        print(f"  关键词：{search_keyword}")
        print(f"  目标获取：第 {target_ip_rank} 新的有效组播IP")
        print(f"  选中IP：{target_ip}")
        print(f"  M3U文件路径：{M3U_PATH}")
        print(f"  GitHub订阅链接：{github_link}")

    except Exception as e:
        print(f"\n❌ 流程出错：{str(e)}")

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
        if github_link:
            print(f"\n【订阅链接】{github_link}")


if __name__ == "__main__":
    keyword, rank = get_runtime_config()
    extract_m3u(keyword, rank)
