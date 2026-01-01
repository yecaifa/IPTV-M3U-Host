# -*- coding: utf-8 -*-
"""
iptv_m3u_get_chrome.py
- Chrome + Selenium（兼容本地/CI）
- 支持运行时输入 / 环境变量配置：SEARCH_KEYWORD, TARGET_IP_RANK
- 支持批量省份模式：BATCH=1 -> 输出到 m3u/<省>.m3u
- 保持“模拟点击”流程：进入IP详情页 -> 查看频道列表 -> M3U下载
- 在 m3u 顶部写入 source_ip 标记（可关）
"""

import os
import re
import time
import urllib.parse
from typing import Optional, Tuple, Dict, List

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

# 是否在 m3u 顶部写入本次来源标记（保证换IP/换rank有diff，播放器一般不受影响）
ENABLE_STAMP = True

# 仓库路径 & 输出目录
GITHUB_REPO_PATH = os.path.dirname(os.path.abspath(__file__))
GITHUB_M3U_FILE_NAME = "iptv_latest.m3u"  # 单次模式输出
M3U_PATH = os.path.join(GITHUB_REPO_PATH, GITHUB_M3U_FILE_NAME)

OUTPUT_DIR = os.path.join(GITHUB_REPO_PATH, "m3u")  # 批量模式输出目录
os.makedirs(OUTPUT_DIR, exist_ok=True)
# ============================================================================


# ===================== 省份列表（可按需增删/改关键词格式）=====================
PROVINCES = [
    "北京", "天津", "上海", "重庆",
    "河北", "山西", "辽宁", "吉林", "黑龙江",
    "江苏", "浙江", "安徽", "福建", "江西", "山东",
    "河南", "湖北", "湖南", "广东", "海南",
    "四川", "贵州", "云南", "陕西", "甘肃", "青海",
    "内蒙古", "广西", "西藏", "宁夏", "新疆",
    "香港", "澳门",
]
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

    # Headless / 自动化兼容增强（尽量像真实浏览器）
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    # 下载目录设置（Linux/Windows 都生效）
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    options.add_experimental_option("prefs", prefs)

    # webdriver-manager 拉取 chromedriver（本地若网络受限可能失败；Actions 通常没问题）
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


def wait_for_dynamic_content(driver: webdriver.Chrome, timeout_sec: int = 25):
    """等待动态内容出现（headless 下重要）"""
    try:
        WebDriverWait(driver, timeout_sec).until(
            EC.presence_of_element_located(
                (By.XPATH, "//*[contains(., 'Multicast IPTV') or contains(., '组播')]")
            )
        )
    except Exception:
        pass


def snapshot_m3u_mtimes(download_dir: str) -> Dict[str, float]:
    """记录当前目录所有 .m3u 的 mtime，用于识别“新下载”的文件"""
    snap: Dict[str, float] = {}
    try:
        for f in os.listdir(download_dir):
            if f.lower().endswith(".m3u"):
                full = os.path.join(download_dir, f)
                try:
                    snap[f] = os.path.getmtime(full)
                except Exception:
                    pass
    except Exception:
        pass
    return snap


def wait_for_new_m3u_file(download_dir: str, before_snapshot: Dict[str, float], click_time: float,
                          timeout_sec: int = 180) -> Optional[str]:
    """
    等待“新下载”的 m3u：
    - 优先：出现一个 before_snapshot 中不存在的新文件
    - 次优：已有 m3u 文件的 mtime 变得比 click_time 更新（或比旧值更大）
    """
    deadline = time.time() + timeout_sec

    def list_m3u() -> List[Tuple[str, float, int, str]]:
        out = []
        try:
            files = os.listdir(download_dir)
        except Exception:
            files = []
        for f in files:
            if not f.lower().endswith(".m3u"):
                continue
            full = os.path.join(download_dir, f)
            try:
                out.append((f, os.path.getmtime(full), os.path.getsize(full), full))
            except Exception:
                continue
        return out

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
                updated_files.append((mtime, full))
            elif mtime > click_time + 0.5:
                updated_files.append((mtime, full))

        if updated_files:
            updated_files.sort(reverse=True)
            return updated_files[0][1]

        time.sleep(1)

    return None


def stamp_m3u(path: str, target_ip: str, target_ip_rank: int):
    """在 m3u 头部写入本次来源标记（纯注释，通常不影响播放器）"""
    if not ENABLE_STAMP:
        return
    try:
        stamp = f"# source_ip={target_ip} rank={target_ip_rank} updated_at={time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        lines = content.splitlines(True)
        # 移除旧 stamp
        lines = [ln for ln in lines if not ln.startswith("# source_ip=")]

        if lines and lines[0].startswith("#EXTM3U"):
            lines.insert(1, stamp)
        else:
            lines.insert(0, stamp)

        with open(path, "w", encoding="utf-8") as f:
            f.write("".join(lines))
    except Exception:
        pass


def extract_m3u(driver: webdriver.Chrome, search_keyword: str, target_ip_rank: int, output_path: str) -> bool:
    """
    单次抓取：
    - 搜索 keyword
    - 在 Multicast IPTV 中找“有效组播IP”
    - 选择第 rank 个
    - 模拟点击下载 m3u
    - 输出到 output_path
    返回：成功 True / 失败 False（失败不抛异常，方便批量继续）
    """
    try:
        print(f"\n========== 开始：{search_keyword} -> {os.path.relpath(output_path, GITHUB_REPO_PATH)} ==========")

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
                if not row_text or "组播" not in row_text:
                    continue

                m_ip = ip_pattern_anywhere.search(row_text)
                if not m_ip:
                    continue
                ip = m_ip.group(1)

                if ip in seen_ip:
                    continue

                # 找可点击链接（保持后续 click 逻辑）
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
            print("  ❌ 未找到任何有效的组播IP，跳过")
            return False

        multicast_items.sort(key=lambda x: x["sort_key"])

        # 打印前10个（避免日志过长）
        print("  📋 有效组播IP列表（前10个，1=最新）：")
        for idx, item in enumerate(multicast_items[:10], start=1):
            mark = "【目标】" if idx == target_ip_rank else ""
            print(f"    第{idx}名：{item['ip']}  状态：{item['status']} {mark}")

        if target_ip_rank < 1 or target_ip_rank > len(multicast_items):
            print(f"  ❌ 目标IP排名超出范围：有效={len(multicast_items)}，目标={target_ip_rank}，跳过")
            return False

        target = multicast_items[target_ip_rank - 1]
        target_ip = target["ip"]
        target_link = target["link"]
        print(f"  ✅ 选中：{target_ip}（{target['status']}）")

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

        # 切换到新窗口
        driver.switch_to.window(driver.window_handles[-1])
        time.sleep(FIXED_DELAY * 2)

        # 6) 点击“M3U下载”
        print("【步骤6】点击M3U下载")

        # 点击前快照，确保抓到“新下载文件”
        before_snapshot = snapshot_m3u_mtimes(GITHUB_REPO_PATH)

        m3u_download_btn = WebDriverWait(driver, ELEMENT_TIMEOUT).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'M3U下载')]"))
        )
        click_time = time.time()
        m3u_download_btn.click()

        # 7) 等待新 m3u 出现
        print("【步骤7】等待下载完成")
        downloaded = wait_for_new_m3u_file(GITHUB_REPO_PATH, before_snapshot, click_time, timeout_sec=180)
        if not downloaded or not os.path.exists(downloaded) or os.path.getsize(downloaded) == 0:
            print("  ❌ 未检测到新的 .m3u 文件，跳过")
            return False

        # 覆盖写入 output_path
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        if os.path.abspath(downloaded) != os.path.abspath(output_path):
            os.replace(downloaded, output_path)

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            print("  ❌ 输出文件为空，跳过")
            return False

        # 写入来源标记
        stamp_m3u(output_path, target_ip, target_ip_rank)

        print(f"✅ 输出成功：{output_path}")
        return True

    except Exception as e:
        print(f"  ❌ 发生异常，跳过：{e}")
        return False

    finally:
        # 回到主窗口，继续下一轮（批量非常关键）
        try:
            if driver and len(driver.window_handles) > 1:
                # 关闭除第一个以外的窗口，避免越开越多
                main = driver.window_handles[0]
                for h in driver.window_handles[1:]:
                    try:
                        driver.switch_to.window(h)
                        driver.close()
                    except Exception:
                        pass
                driver.switch_to.window(main)
        except Exception:
            pass


def run_single(keyword: str, rank: int) -> int:
    """单次模式：输出 iptv_latest.m3u"""
    print(f"【模式】单次模式：keyword={keyword} rank={rank}")
    print(f"【输出】{M3U_PATH}")

    driver = None
    try:
        driver = make_driver(download_dir=GITHUB_REPO_PATH)
        ok = extract_m3u(driver, keyword, rank, M3U_PATH)
        return 0 if ok else 2
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def run_batch(rank: int, keyword_template: str) -> int:
    """
    批量模式：每省一个文件输出到 m3u/<省>.m3u
    keyword_template:
      - 默认 "{province}"：例如 "湖北"
      - 可改为 "{province}省" / "{province}移动" / "{province}武汉" 这种更精确格式
    """
    print(f"【模式】批量省份模式：rank={rank} template={keyword_template}")
    print(f"【输出目录】{OUTPUT_DIR}")

    driver = None
    success = 0
    total = 0

    try:
        driver = make_driver(download_dir=GITHUB_REPO_PATH)

        for p in PROVINCES:
            total += 1
            kw = keyword_template.replace("{province}", p).strip()
            out = os.path.join(OUTPUT_DIR, f"{p}.m3u")

            ok = extract_m3u(driver, kw, rank, out)
            if ok:
                success += 1

        print(f"\n【批量完成】成功 {success}/{total}")
        return 0 if success > 0 else 2

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    keyword, rank = get_runtime_config()

    batch = (os.getenv("BATCH") or "0").strip() in ("1", "true", "True")
    keyword_template = (os.getenv("KEYWORD_TEMPLATE") or "{province}").strip()

    print(f"【路径验证】仓库目录：{GITHUB_REPO_PATH}")
    print(f"【路径验证】是否为Git仓库：{os.path.exists(os.path.join(GITHUB_REPO_PATH, '.git'))}")
    print(f"【当前配置】BATCH={batch}  HEADLESS={os.getenv('HEADLESS','1')}  rank={rank}")

    if batch:
        raise SystemExit(run_batch(rank=rank, keyword_template=keyword_template))
    else:
        raise SystemExit(run_single(keyword=keyword, rank=rank))
