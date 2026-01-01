# -*- coding: utf-8 -*-
"""
iptv_m3u_get_chrome.py
- Chrome + Selenium（兼容本地/CI）
- 支持运行时输入 / 环境变量配置：SEARCH_KEYWORD, TARGET_IP_RANK
- 支持批量模式（BATCH=1）：每省生成 m3u/<省>.m3u
- 【关键修改】批量模式优先：从页面获取 token -> 拼接 URL ?token=...&t=all&province=xx&limit=6
  - token URL 成功：不依赖关键词/不依赖下拉框 DOM
  - token URL 失败：回退下拉框（provinceSelect）
  - 下拉框失败：回退关键词 KEYWORD_TEMPLATE
"""

import os
import re
import time
import urllib.parse
import platform
from typing import Optional, Tuple, List, Dict

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager


# ===================== 默认配置（可被环境变量/输入覆盖）=====================
DEFAULT_SEARCH_KEYWORD = "湖北省武汉"
DEFAULT_TARGET_IP_RANK = 1

HOME_PAGE_URL = "https://iptv.cqshushu.com"
ELEMENT_TIMEOUT = 60
PAGE_LOAD_TIMEOUT = 120
FIXED_DELAY = 2

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "m3u")
ENABLE_STAMP = True

# 省份代码（来自你截图 option value）
# 说明：all=全部；vn=越南；kr=韩国；tw=台湾；hk=香港；mo=澳门（你截图里部分为 tw）
PROVINCE_CODE_MAP: Dict[str, str] = {
    "bj": "北京",
    "tj": "天津",
    "sh": "上海",
    "cq": "重庆",
    "hb": "湖北",
    "he": "河北",
    "hn": "湖南",
    "gd": "广东",
    "gx": "广西",
    "hi": "海南",
    "sc": "四川",
    "js": "江苏",
    "sd": "山东",
    "ah": "安徽",
    "fj": "福建",
    "jx": "江西",
    "sn": "陕西",
    "ha": "河南",
    "jl": "吉林",
    "zj": "浙江",
    "nm": "内蒙古",
    "xj": "新疆",
    "qh": "青海",
    "gs": "甘肃",
    "nx": "宁夏",
    "hl": "黑龙江",
    "ln": "辽宁",
    "gz": "贵州",
    "yn": "云南",
    "sx": "山西",
    "gx2": "广西(备用)",  # 防冲突占位，不会用
    # 特殊/海外（可选跑）
    "kr": "韩国",
    "vn": "越南",
    "tw": "台湾",
    "hk": "香港",
    "mo": "澳门",
}

# 你想跑哪些（默认：只跑国内省级 + 直辖市，不跑海外/港澳台的话就从列表剔除）
BATCH_PROVINCE_CODES: List[str] = [
    "bj","tj","sh","cq",
    "he","sx","nm",
    "ln","jl","hl",
    "js","zj","ah","fj","jx","sd",
    "ha","hb","hn","gd","gx","hi",
    "sc","gz","yn",
    "sn","gs","qh","nx","xj",
    # "hk","mo","tw",  # 如需港澳台可取消注释
    # "kr","vn",       # 如需海外可取消注释
]
# ============================================================================


def get_runtime_config() -> Tuple[str, int]:
    kw_env = (os.getenv("SEARCH_KEYWORD") or "").strip()
    rk_env = (os.getenv("TARGET_IP_RANK") or "").strip()

    keyword = kw_env if kw_env else DEFAULT_SEARCH_KEYWORD
    rank = DEFAULT_TARGET_IP_RANK
    if rk_env.isdigit():
        rank = int(rk_env)

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
    headless_env = (os.getenv("HEADLESS") or "1").strip()
    headless = headless_env not in ("0", "false", "False")

    options = ChromeOptions()

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

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")

    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    }
    options.add_experimental_option("prefs", prefs)

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

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
    try:
        WebDriverWait(driver, timeout_sec).until(
            EC.presence_of_element_located(
                (By.XPATH, "//*[contains(., 'Multicast IPTV') or contains(., '组播')]")
            )
        )
    except Exception:
        pass


def get_token_from_current_url(driver: webdriver.Chrome) -> Optional[str]:
    """
    从当前 URL 提取 token 参数
    例如：https://iptv.cqshushu.com/?token=xxxx&t=all&province=hb&limit=6
    """
    try:
        url = driver.current_url or ""
        if "token=" not in url:
            return None
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        token = (qs.get("token") or [None])[0]
        if token and re.fullmatch(r"[0-9a-fA-F]{16,64}", token):
            return token
        return token  # 不强校验也行
    except Exception:
        return None


def build_filter_url(token: str, province_code: str, limit: int = 6, t: str = "all") -> str:
    q = urllib.parse.urlencode({
        "token": token,
        "t": t,
        "province": province_code,
        "limit": str(limit),
    })
    return f"{HOME_PAGE_URL}/?{q}"


def wait_for_new_m3u_file(download_dir: str, before_snapshot: dict, click_time: float, timeout_sec: int = 90) -> Optional[str]:
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
                m3us.append((name, mtime, size, full))
        except Exception:
            m3us = []

        updated_files = []
        for name, mtime, size, full in m3us:
            if size <= 0:
                continue
            old_mtime = before_snapshot.get(name)
            if old_mtime is None and mtime > click_time - 0.5:
                updated_files.append((mtime, full))
            elif old_mtime is not None and mtime > old_mtime + 0.5:
                updated_files.append((mtime, full))
            elif mtime > click_time + 0.5:
                updated_files.append((mtime, full))

        if updated_files:
            updated_files.sort(reverse=True)
            return updated_files[0][1]

        time.sleep(1)

    return None


def stamp_m3u(path: str, target_ip: str, target_ip_rank: int):
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


def _extract_and_download_from_current_page(driver: webdriver.Chrome, target_ip_rank: int, output_path: str) -> bool:
    try:
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

        # 4) 进入IP详情页
        print(f"【步骤4】进入IP详情页：{target_ip}")
        target_link.click()
        WebDriverWait(driver, ELEMENT_TIMEOUT).until(EC.staleness_of(target_link))
        time.sleep(FIXED_DELAY * 2)

        # 5) 查看频道列表
        print("【步骤5】点击查看频道列表")
        channel_btn = WebDriverWait(driver, ELEMENT_TIMEOUT).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), '查看频道列表')]"))
        )
        channel_btn.click()

        driver.switch_to.window(driver.window_handles[-1])
        time.sleep(FIXED_DELAY * 2)

        # 6) 下载
        print("【步骤6】点击M3U下载")
        before_snapshot = {}
        base_dir = os.path.dirname(os.path.abspath(__file__))
        try:
            for name in os.listdir(base_dir):
                if name.lower().endswith(".m3u"):
                    full = os.path.join(base_dir, name)
                    try:
                        before_snapshot[name] = os.path.getmtime(full)
                    except Exception:
                        pass
        except Exception:
            pass

        m3u_download_btn = WebDriverWait(driver, ELEMENT_TIMEOUT).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'M3U下载')]"))
        )
        click_time = time.time()
        m3u_download_btn.click()

        print("【步骤7】等待下载完成")
        downloaded = wait_for_new_m3u_file(base_dir, before_snapshot, click_time, timeout_sec=90)
        if not downloaded or not os.path.exists(downloaded) or os.path.getsize(downloaded) <= 0:
            print("  ❌ 未检测到有效的下载 m3u，跳过")
            return False

        out_dir = os.path.dirname(output_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        # 覆盖输出
        if os.path.abspath(downloaded) != os.path.abspath(output_path):
            with open(downloaded, "rb") as fr, open(output_path, "wb") as fw:
                fw.write(fr.read())

        if not os.path.exists(output_path) or os.path.getsize(output_path) <= 0:
            print("  ❌ 输出文件为空/不存在，跳过")
            return False

        stamp_m3u(output_path, target_ip, target_ip_rank)

        print(f"✅ 输出成功：{output_path}")
        return True

    except Exception as e:
        print(f"  ❌ 发生异常，跳过：{e}")
        return False

    finally:
        # 关闭多余窗口，回主窗口
        try:
            if driver and len(driver.window_handles) > 1:
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


def do_search(driver: webdriver.Chrome, keyword: str):
    print(f"【步骤2】搜索：{keyword}")
    try:
        search_input = driver.find_element(By.NAME, "q")
        search_input.clear()
        search_input.send_keys(keyword)
        search_input.submit()
    except Exception:
        encoded_key = urllib.parse.quote(keyword)
        driver.get(f"{HOME_PAGE_URL}?q={encoded_key}")

    time.sleep(FIXED_DELAY * 2)
    wait_for_dynamic_content(driver, timeout_sec=25)


def try_select_province_dropdown(driver: webdriver.Chrome, province_text: str) -> bool:
    """下拉框方式（兜底）"""
    try:
        driver.get(HOME_PAGE_URL)
        time.sleep(FIXED_DELAY * 2)

        sel_el = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "provinceSelect"))
        )
        sel = Select(sel_el)

        old_marker = None
        try:
            old_marker = driver.find_element(By.TAG_NAME, "body")
        except Exception:
            old_marker = None

        sel.select_by_visible_text(province_text)

        if old_marker is not None:
            try:
                WebDriverWait(driver, 10).until(EC.staleness_of(old_marker))
            except Exception:
                pass

        time.sleep(FIXED_DELAY * 2)
        wait_for_dynamic_content(driver, timeout_sec=25)

        print(f"【步骤2】区域选择（下拉框）：{province_text}")
        return True
    except Exception:
        return False


def try_open_by_token_url(driver: webdriver.Chrome, province_code: str) -> bool:
    """
    token URL 方式（优先）
    - 先打开首页拿 token（或复用已有 token）
    - 拼接筛选 URL 跳转
    """
    try:
        # 如果当前没有 token，打开首页获取一次
        token = get_token_from_current_url(driver)
        if not token:
            driver.get(HOME_PAGE_URL)
            time.sleep(FIXED_DELAY * 2)
            wait_for_dynamic_content(driver, timeout_sec=10)
            token = get_token_from_current_url(driver)

        if not token:
            return False

        url = build_filter_url(token=token, province_code=province_code, limit=6, t="all")
        driver.get(url)
        time.sleep(FIXED_DELAY * 2)
        wait_for_dynamic_content(driver, timeout_sec=25)
        print(f"【步骤2】区域选择（token URL）：province={province_code} url={url}")
        return True
    except Exception:
        return False


def run_single(keyword: str, rank: int) -> int:
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "iptv_latest.m3u")
    print(f"【模式】单次模式：keyword={keyword} rank={rank}")
    print(f"【输出】{out}")

    driver = None
    try:
        driver = make_driver(download_dir=os.path.dirname(os.path.abspath(__file__)))
        driver.get(HOME_PAGE_URL)
        time.sleep(FIXED_DELAY * 2)
        do_search(driver, keyword)
        ok = _extract_and_download_from_current_page(driver, target_ip_rank=rank, output_path=out)
        return 0 if ok else 2
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def run_batch(rank: int, keyword_template: str) -> int:
    print(f"【模式】批量省份模式：rank={rank} template={keyword_template}")
    print(f"【输出目录】{OUTPUT_DIR}")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    driver = None
    success = 0
    total = 0

    try:
        driver = make_driver(download_dir=os.path.dirname(os.path.abspath(__file__)))

        # 先打开一次首页，尽可能提前拿到 token（提高命中率）
        driver.get(HOME_PAGE_URL)
        time.sleep(FIXED_DELAY * 2)

        for code in BATCH_PROVINCE_CODES:
            total += 1
            name = PROVINCE_CODE_MAP.get(code, code)
            out = os.path.join(OUTPUT_DIR, f"{name}.m3u")

            print(f"\n========== 开始：{name}({code}) -> m3u/{name}.m3u ==========")

            ok = False

            # 1) 优先 token URL
            ok = try_open_by_token_url(driver, code)

            # 2) token URL 失败：回退下拉框（用中文名）
            if not ok and name and name != code:
                ok = try_select_province_dropdown(driver, name)

            # 3) 再失败：回退关键词模板
            if not ok:
                kw = keyword_template.replace("{province}", name).strip()
                driver.get(HOME_PAGE_URL)
                time.sleep(FIXED_DELAY * 2)
                do_search(driver, kw)

            # 进入提取+下载
            ok2 = _extract_and_download_from_current_page(driver, target_ip_rank=rank, output_path=out)
            if ok2:
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
    print("=== SCRIPT START ===", flush=True)
    print("HEADLESS=", os.getenv("HEADLESS"), "BATCH=", os.getenv("BATCH"), flush=True)

    keyword, rank = get_runtime_config()
    batch = (os.getenv("BATCH") or "0").strip() in ("1", "true", "True")
    keyword_template = (os.getenv("KEYWORD_TEMPLATE") or "{province}省").strip()

    print(f"【路径验证】仓库目录：{os.path.dirname(os.path.abspath(__file__))}")
    print(f"【当前配置】BATCH={batch}  HEADLESS={os.getenv('HEADLESS','1')}  rank={rank}")

    if batch:
        raise SystemExit(run_batch(rank=rank, keyword_template=keyword_template))
    else:
        raise SystemExit(run_single(keyword=keyword, rank=rank))
