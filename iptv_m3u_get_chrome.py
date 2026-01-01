# -*- coding: utf-8 -*-
"""
iptv_m3u_get_chrome.py
- Chrome + Selenium（兼容本地/CI）
- 支持运行时输入 / 环境变量配置：SEARCH_KEYWORD, TARGET_IP_RANK
- Headless 兼容增强（更像真实浏览器 + 显式等待动态内容）
- 保持“模拟点击”流程：进入IP详情页 -> 查看频道列表 -> M3U下载
- GitHub Actions 批量：沿用【旧的搜索模式】（模拟输入框搜索/或 ?q= URL），不依赖 token/provinceSelect
- 输出：
  - single：iptv_latest.m3u
  - batch：m3u/<名称>.m3u（自动创建 m3u 目录）
"""

import os
import re
import time
import urllib.parse
import platform
from typing import Optional, Tuple, List

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager


# ===================== 默认配置（可被环境变量/输入覆盖）=====================
DEFAULT_SEARCH_KEYWORD = "湖北省武汉"
DEFAULT_TARGET_IP_RANK = 1  # 获取“有效组播IP”里的第n新（1=最新）

HOME_PAGE_URL = "https://iptv.cqshushu.com"
ELEMENT_TIMEOUT = 60
PAGE_LOAD_TIMEOUT = 120
FIXED_DELAY = 2

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "m3u")
SINGLE_OUT = os.path.join(BASE_DIR, "iptv_latest.m3u")

# 每省/市最多耗时（防止 Action 卡死）
MAX_PROVINCE_SECONDS = int(os.getenv("MAX_PROVINCE_SECONDS", "120"))

# 给输出加注释（方便你确认选中 IP/排名/更新时间）
ENABLE_STAMP = True

# 批量关键词列表： (输出文件名, 搜索关键词)
# 你可以按你的经验微调关键词（例如某些省要加“省”字更稳定）
BATCH_KEYWORDS: List[Tuple[str, str]] = [
    ("北京", "北京市"),
    ("上海", "上海市"),
    ("天津", "天津市"),
    ("重庆", "重庆市"),

    ("河北", "河北省"),
    ("山西", "山西省"),
    ("内蒙古", "内蒙古"),
    ("辽宁", "辽宁省"),
    ("吉林", "吉林省"),
    ("黑龙江", "黑龙江省"),

    ("江苏", "江苏省"),
    ("浙江", "浙江省"),
    ("安徽", "安徽省"),
    ("福建", "福建省"),
    ("江西", "江西省"),
    ("山东", "山东省"),

    ("河南", "河南省"),
    ("湖北", "湖北省"),
    ("湖南", "湖南省"),
    ("广东", "广东省"),
    ("广西", "广西"),
    ("海南", "海南省"),

    ("四川", "四川省"),
    ("贵州", "贵州省"),
    ("云南", "云南省"),
    ("陕西", "陕西省"),
    ("甘肃", "甘肃省"),
    ("青海", "青海省"),
    ("宁夏", "宁夏"),
    ("新疆", "新疆"),
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
    headless_env = (os.getenv("HEADLESS") or "1").strip()
    headless = headless_env not in ("0", "false", "False")

    options = ChromeOptions()

    # 避免某些资源加载卡死（更快返回 DOM）
    options.page_load_strategy = "eager"

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


def wait_for_dynamic_content(driver: webdriver.Chrome, timeout_sec: int = 20):
    """等待页面出现“Multicast IPTV/组播”等动态内容（等不到也不直接失败）"""
    try:
        WebDriverWait(driver, timeout_sec).until(
            EC.presence_of_element_located(
                (By.XPATH, "//*[contains(., 'Multicast IPTV') or contains(., '组播')]")
            )
        )
    except Exception:
        pass


def snapshot_m3u_mtime(download_dir: str) -> dict:
    snap = {}
    try:
        for name in os.listdir(download_dir):
            if name.lower().endswith(".m3u"):
                full = os.path.join(download_dir, name)
                try:
                    snap[name] = os.path.getmtime(full)
                except Exception:
                    pass
    except Exception:
        pass
    return snap


def wait_for_new_m3u_file(download_dir: str, before_snapshot: dict, click_time: float, timeout_sec: int = 90) -> Optional[str]:
    """等待下载完成：找到“新出现/被更新”的 m3u 文件路径"""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        m3us = []
        try:
            for name in os.listdir(download_dir):
                if not name.lower().endswith(".m3u"):
                    continue
                full = os.path.join(download_dir, name)
                try:
                    mtime = os.path.getmtime(full)
                    size = os.path.getsize(full)
                except Exception:
                    continue
                if size <= 0:
                    continue
                m3us.append((mtime, name, full))
        except Exception:
            m3us = []

        updated = []
        for mtime, name, full in m3us:
            old = before_snapshot.get(name)
            if old is None and mtime > click_time - 0.5:
                updated.append((mtime, full))
            elif old is not None and mtime > old + 0.5:
                updated.append((mtime, full))
            elif mtime > click_time + 0.5:
                updated.append((mtime, full))

        if updated:
            updated.sort(reverse=True)
            return updated[0][1]

        time.sleep(1)
    return None


def stamp_m3u(path: str, target_ip: str, target_ip_rank: int):
    """在 m3u 顶部插入一行注释，方便你确认选中来源"""
    if not ENABLE_STAMP:
        return
    try:
        stamp = f"# source_ip={target_ip} rank={target_ip_rank} updated_at={time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        lines = content.splitlines(True)
        lines = [ln for ln in lines if not ln.startswith("# source_ip=")]

        if lines and lines[0].startswith("#EXTM3U"):
            lines.insert(1, stamp)
        else:
            lines.insert(0, stamp)

        with open(path, "w", encoding="utf-8") as f:
            f.write("".join(lines))
    except Exception:
        pass


def do_search(driver: webdriver.Chrome, keyword: str):
    """沿用旧逻辑：模拟搜索框 + submit；失败则用 ?q= URL"""
    print(f"【步骤2】搜索：{keyword}", flush=True)
    try:
        search_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "q"))
        )
        search_input.clear()
        search_input.send_keys(keyword)
        search_input.submit()
    except Exception:
        encoded_key = urllib.parse.quote(keyword)
        driver.get(f"{HOME_PAGE_URL}?q={encoded_key}")

    time.sleep(FIXED_DELAY * 2)
    wait_for_dynamic_content(driver, timeout_sec=20)


def close_extra_windows(driver: webdriver.Chrome):
    """关闭多余窗口，回到主窗口"""
    try:
        if len(driver.window_handles) > 1:
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


def extract_and_download_from_current_page(driver: webdriver.Chrome, target_ip_rank: int, output_path: str) -> bool:
    """
    在当前页面：
    - 提取 Multicast IPTV 中有效组播IP
    - 选第 N 新（新上线优先，其次存活天数小）
    - 模拟点击：IP详情 -> 查看频道列表 -> M3U下载
    - 输出到 output_path
    """
    try:
        print("【步骤3】提取 Multicast IPTV 中有效的组播IP...", flush=True)

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

        # 尝试定位 Multicast IPTV 区域；失败则回退全页找含“组播”的行
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

        print(f"  ✅ 提取到 {len(multicast_items)} 个有效组播IP", flush=True)
        if not multicast_items:
            print("  ❌ 未找到任何有效组播IP，跳过", flush=True)
            return False

        multicast_items.sort(key=lambda x: x["sort_key"])

        print("  📋 有效组播IP列表（前10个，1=最新）：", flush=True)
        for idx, item in enumerate(multicast_items[:10], start=1):
            mark = "【目标】" if idx == target_ip_rank else ""
            print(f"    第{idx}名：{item['ip']}  状态：{item['status']} {mark}", flush=True)

        if target_ip_rank < 1 or target_ip_rank > len(multicast_items):
            print(f"  ❌ 目标排名超范围：有效={len(multicast_items)} 目标={target_ip_rank}", flush=True)
            return False

        target = multicast_items[target_ip_rank - 1]
        target_ip = target["ip"]
        target_link = target["link"]
        print(f"  ✅ 选中：{target_ip}（{target['status']}）", flush=True)

        # 进入IP详情页（模拟点击）
        print(f"【步骤4】进入IP详情页：{target_ip}", flush=True)
        target_link.click()
        WebDriverWait(driver, ELEMENT_TIMEOUT).until(EC.staleness_of(target_link))
        time.sleep(FIXED_DELAY * 2)

        # 点击“查看频道列表”
        print("【步骤5】点击查看频道列表", flush=True)
        channel_btn = WebDriverWait(driver, ELEMENT_TIMEOUT).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), '查看频道列表')]"))
        )
        channel_btn.click()

        # 切换到新页面
        driver.switch_to.window(driver.window_handles[-1])
        time.sleep(FIXED_DELAY * 2)

        # 点击“M3U下载”
        print("【步骤6】点击M3U下载", flush=True)
        before_snapshot = snapshot_m3u_mtime(BASE_DIR)
        m3u_download_btn = WebDriverWait(driver, ELEMENT_TIMEOUT).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'M3U下载')]"))
        )
        click_time = time.time()
        m3u_download_btn.click()

        print("【步骤7】等待下载完成", flush=True)
        downloaded = wait_for_new_m3u_file(BASE_DIR, before_snapshot, click_time, timeout_sec=90)
        if not downloaded or not os.path.exists(downloaded) or os.path.getsize(downloaded) <= 0:
            print("  ❌ 未检测到有效下载 m3u", flush=True)
            return False

        # 确保输出目录存在
        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        # 写入输出（覆盖）
        if os.path.abspath(downloaded) != os.path.abspath(output_path):
            with open(downloaded, "rb") as fr, open(output_path, "wb") as fw:
                fw.write(fr.read())

        if not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
            print("  ❌ 输出文件为空/不存在", flush=True)
            return False

        stamp_m3u(output_path, target_ip, target_ip_rank)

        print(f"✅ 输出成功：{output_path}", flush=True)
        return True

    except Exception as e:
        print(f"  ❌ 异常：{e}", flush=True)
        return False

    finally:
        # 关闭多余窗口，回到主窗口
        close_extra_windows(driver)


def run_single(keyword: str, rank: int) -> int:
    print(f"【模式】single：keyword={keyword} rank={rank}", flush=True)
    driver = None
    try:
        driver = make_driver(download_dir=BASE_DIR)
        print(f"【步骤1】打开首页：{HOME_PAGE_URL}", flush=True)
        driver.get(HOME_PAGE_URL)
        time.sleep(FIXED_DELAY * 2)

        do_search(driver, keyword)
        ok = extract_and_download_from_current_page(driver, target_ip_rank=rank, output_path=SINGLE_OUT)
        return 0 if ok else 2
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def run_batch(rank: int) -> int:
    print(f"【模式】batch：rank={rank} MAX_PROVINCE_SECONDS={MAX_PROVINCE_SECONDS}", flush=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    driver = None
    success = 0
    total = 0

    try:
        driver = make_driver(download_dir=BASE_DIR)

        for name, keyword in BATCH_KEYWORDS:
            total += 1
            out = os.path.join(OUTPUT_DIR, f"{name}.m3u")

            print(f"\n========== 开始：{name} -> m3u/{name}.m3u ==========", flush=True)
            province_start = time.time()

            try:
                # 旧模式：每次从首页开始 -> 模拟搜索
                driver.get(HOME_PAGE_URL)
                time.sleep(FIXED_DELAY * 2)

                if time.time() - province_start > MAX_PROVINCE_SECONDS:
                    print(f"  ⚠️ {name} 超时，跳过", flush=True)
                    continue

                do_search(driver, keyword)

                if time.time() - province_start > MAX_PROVINCE_SECONDS:
                    print(f"  ⚠️ {name} 超时，跳过", flush=True)
                    continue

                ok = extract_and_download_from_current_page(driver, target_ip_rank=rank, output_path=out)

                if ok:
                    success += 1

            except Exception as e:
                print(f"  ❌ {name} 处理异常：{e}", flush=True)
                continue

        print(f"\n【批量完成】成功 {success}/{total}", flush=True)
        return 0 if success > 0 else 2

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    print("=== SCRIPT START ===", flush=True)
    keyword, rank = get_runtime_config()

    batch = (os.getenv("BATCH") or "0").strip() in ("1", "true", "True")
    print(f"【当前配置】BATCH={batch} HEADLESS={os.getenv('HEADLESS','1')} rank={rank}", flush=True)

    if batch:
        raise SystemExit(run_batch(rank=rank))
    else:
        raise SystemExit(run_single(keyword=keyword, rank=rank))
