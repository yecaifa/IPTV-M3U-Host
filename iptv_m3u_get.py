from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from git import Repo
import re
import os
import time
import urllib.parse

# ===================== 配置项（默认值）=====================
DEFAULT_SEARCH_KEYWORD = "湖北省武汉"
DEFAULT_TARGET_IP_RANK = 1

HOME_PAGE_URL = "https://iptv.cqshushu.com"
ELEMENT_TIMEOUT = 60
PAGE_LOAD_TIMEOUT = 120
FIXED_DELAY = 3
# ==========================================================


# GitHub配置
GITHUB_REPO_PATH = os.path.dirname(__file__)
GITHUB_M3U_FILE_NAME = "iptv_latest.m3u"
GITHUB_BRANCH = "main"
YOUR_GITHUB_USERNAME = "yecaifa"

# 文件路径
M3U_PATH = os.path.join(GITHUB_REPO_PATH, GITHUB_M3U_FILE_NAME)
# ============================================================

# 路径验证
print(f"【路径验证】仓库目录：{GITHUB_REPO_PATH}")
print(f"【路径验证】M3U文件路径：{M3U_PATH}")
print(f"【路径验证】是否为Git仓库：{os.path.exists(os.path.join(GITHUB_REPO_PATH, '.git'))}")


def upload_m3u_to_github():
    """仅上传/更新 M3U 文件到GitHub（只提交 iptv_latest.m3u）"""
    try:
        if not os.path.exists(GITHUB_REPO_PATH) or not os.path.exists(os.path.join(GITHUB_REPO_PATH, ".git")):
            raise Exception("当前目录不是Git仓库（缺少.git）")
        if not os.path.exists(M3U_PATH):
            raise Exception("M3U文件不存在，无法提交")

        repo = Repo(GITHUB_REPO_PATH)
        git = repo.git

        # 确保 origin 存在
        if "origin" not in [r.name for r in repo.remotes]:
            raise Exception("未配置远程 origin，请先设置远程仓库")

        # 只 add 目标 m3u 文件
        git.add(GITHUB_M3U_FILE_NAME)

        # 只判断这个文件是否有变更（避免其它文件变更触发提交）
        changed = repo.index.diff("HEAD")  # staged diff
        changed_files = {d.a_path for d in changed}

        # HEAD 不存在（首次提交）时，repo.index.diff("HEAD") 可能异常，做兜底
        if not repo.head.is_valid():
            # 首次提交：直接 commit
            commit_msg = f"Update M3U - {time.strftime('%Y-%m-%d %H:%M:%S')}"
            git.commit('-m', commit_msg)
            git.push('origin', GITHUB_BRANCH)
            print(f"✅ GitHub上传成功：{commit_msg}")
            return f"https://raw.githubusercontent.com/{YOUR_GITHUB_USERNAME}/IPTV-M3U-Host/{GITHUB_BRANCH}/{GITHUB_M3U_FILE_NAME}"

        if GITHUB_M3U_FILE_NAME in changed_files:
            commit_msg = f"Update M3U (有效组播第{TARGET_IP_RANK}新IP) - {time.strftime('%Y-%m-%d %H:%M:%S')}"
            git.commit('-m', commit_msg)
            git.push('origin', GITHUB_BRANCH)
            print(f"✅ GitHub上传成功：{commit_msg}")
        else:
            # m3u 没变化就不提交
            print("ℹ️ M3U 文件无变化，无需提交")

        return f"https://raw.githubusercontent.com/{YOUR_GITHUB_USERNAME}/IPTV-M3U-Host/{GITHUB_BRANCH}/{GITHUB_M3U_FILE_NAME}"

    except Exception as e:
        raise Exception(f"GitHub上传失败：{str(e)}")





def extract_m3u():
    if os.path.exists(M3U_PATH):
        os.remove(M3U_PATH)

    driver = None
    github_link = None
    try:
        # 1. 浏览器配置（开启下载监听）
        options = webdriver.EdgeOptions()
        options.add_experimental_option('excludeSwitches', ['enable-logging'])
        options.page_load_strategy = 'normal'
        options.add_argument('--disable-images')
        options.add_argument('--disable-gpu')

        # 配置下载路径为当前仓库目录
        prefs = {
            "download.default_directory": GITHUB_REPO_PATH,
            "download.prompt_for_download": False,  # 自动下载，不弹窗
            "download.directory_upgrade": True
        }
        options.add_experimental_option("prefs", prefs)

        driver = webdriver.Edge(options=options)
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        driver.set_script_timeout(ELEMENT_TIMEOUT)
        driver.maximize_window()

        # 2. 访问首页
        print(f"【步骤1】打开首页：{HOME_PAGE_URL}")
        driver.get(HOME_PAGE_URL)
        time.sleep(FIXED_DELAY * 3)

        # 3. 搜索关键词
        print(f"【步骤2】搜索：{SEARCH_KEYWORD}")
        try:
            search_input = driver.find_element(By.NAME, "q")
            search_input.clear()
            search_input.send_keys(SEARCH_KEYWORD)
            search_input.submit()
        except:
            encoded_key = urllib.parse.quote(SEARCH_KEYWORD)
            driver.get(f"{HOME_PAGE_URL}?q={encoded_key}")
        time.sleep(FIXED_DELAY * 3)

        # 4. 只提取 Multicast IPTV 中“有效”的组播IP，并按“新→旧”排序后取第 n 新
        print(f"【步骤3】提取 Multicast IPTV 中有效的组播IP...")

        ip_pattern_anywhere = re.compile(r'(\d{1,3}(?:\.\d{1,3}){3})')
        alive_days_pattern = re.compile(r'存活\s*(\d+)\s*天')

        def parse_status(text: str):
            """
            返回 (is_valid, sort_key_tuple, status_str, days_or_none)
            sort_key: (0,0)=新上线 最优；(1,days)=存活days；无效=(99,999999)
            """
            t = text.replace("\u3000", " ").strip()
            if "暂时失效" in t:
                return (False, (99, 999999), "暂时失效", None)
            if "新上线" in t:
                return (True, (0, 0), "新上线", 0)
            m = alive_days_pattern.search(t)
            if m:
                days = int(m.group(1))
                return (True, (1, days), f"存活{days}天", days)
            # 未识别到明确状态：为避免误选，按无效处理
            return (False, (99, 999999), t, None)

        # --- 先定位 Multicast IPTV 区域（尽量精确），失败则回退为“只要含组播的行” ---
        multicast_root = None
        try:
            # 常见标题：Multicast IPTV / multicast iptv
            multicast_title = driver.find_element(
                By.XPATH,
                "//*[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'multicast iptv')]"
            )
            multicast_root = multicast_title.find_element(
                By.XPATH,
                "ancestor::*[self::div or self::section or self::main or self::body][1]"
            )
        except:
            multicast_root = None

        if multicast_root:
            candidate_rows = multicast_root.find_elements(By.XPATH, ".//tr | .//li | .//div")
        else:
            # 回退策略：全页面找“含组播关键字”的行（尽量避开 Hotel IPTV）
            candidate_rows = driver.find_elements(By.XPATH, "//*[self::tr or self::li or self::div][contains(., '组播')]")

        multicast_items = []
        seen_ip = set()

        for row in candidate_rows:
            try:
                row_text = row.text.strip()
                if not row_text:
                    continue

                # 类型必须包含“组播”
                if "组播" not in row_text:
                    continue

                # 行里必须有IP
                m_ip = ip_pattern_anywhere.search(row_text)
                if not m_ip:
                    continue
                ip = m_ip.group(1)

                # 去重：保留先遇到的（通常页面越靠上越新）
                if ip in seen_ip:
                    continue

                # 找可点击链接（保持后续 click 逻辑不变）
                link_elem = None
                try:
                    link_elem = row.find_element(By.XPATH, f".//a[normalize-space(text())='{ip}']")
                except:
                    try:
                        link_elem = row.find_element(By.XPATH, f".//a[contains(normalize-space(.), '{ip}')]")
                    except:
                        link_elem = None

                if not link_elem:
                    continue

                # 解析状态（只要有效：新上线 / 存活n天）
                is_valid, sort_key, status_norm, _days = parse_status(row_text)
                if not is_valid:
                    continue

                seen_ip.add(ip)
                multicast_items.append({
                    "ip": ip,
                    "link": link_elem,
                    "row_text": row_text,
                    "status": status_norm,
                    "sort_key": sort_key,
                })

            except:
                continue

        print(f"  ✅ 提取到 {len(multicast_items)} 个有效组播IP（仅Multicast/含组播类型）")

        if len(multicast_items) == 0:
            print("❌ 未找到任何有效的组播IP（可能页面结构变化或全部暂时失效），流程终止")
            return

        # 排序：新上线优先，其次存活天数小的更“新”
        multicast_items.sort(key=lambda x: x["sort_key"])

        # 打印列表（带排名）
        print(f"  📋 有效组播IP列表（排名从1开始，1=最新）：")
        for idx, item in enumerate(multicast_items, start=1):
            mark = "【选中】" if idx == TARGET_IP_RANK else ""
            print(f"    第{idx}名：{item['ip']}  状态：{item['status']} {mark}")

        # 边界判断
        if TARGET_IP_RANK < 1 or TARGET_IP_RANK > len(multicast_items):
            raise Exception(f"❌ 目标IP排名超出范围（有效组播IP数量：{len(multicast_items)}，目标排名：{TARGET_IP_RANK}）")

        # 选择第n新的“有效组播IP”
        target = multicast_items[TARGET_IP_RANK - 1]
        target_ip = target["ip"]
        target_link = target["link"]
        print(f"  ✅ 选中第 {TARGET_IP_RANK} 新的有效组播IP：{target_ip}（{target['status']}）")

        # 5. 进入IP详情页（保持原先模拟点击）
        print(f"【步骤4】进入IP详情页：{target_ip}")
        target_link.click()
        WebDriverWait(driver, ELEMENT_TIMEOUT).until(EC.staleness_of(target_link))
        time.sleep(FIXED_DELAY * 3)

        # 6. 点击“查看频道列表”按钮
        print(f"【步骤5】点击查看频道列表")
        channel_btn = WebDriverWait(driver, ELEMENT_TIMEOUT).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), '查看频道列表')]"))
        )
        channel_btn.click()

        # 切换到新打开的频道列表页面
        driver.switch_to.window(driver.window_handles[-1])
        time.sleep(FIXED_DELAY * 3)

        # 7. 点击“M3U下载”按钮，自动下载M3U文件
        print(f"【步骤6】点击M3U下载")
        m3u_download_btn = WebDriverWait(driver, ELEMENT_TIMEOUT).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'M3U下载')]"))
        )
        m3u_download_btn.click()

        # 等待下载完成
        time.sleep(FIXED_DELAY * 5)

        # 8. 验证M3U文件是否下载成功
        if not os.path.exists(M3U_PATH):
            # 若下载的文件名不是目标名，重命名
            for file in os.listdir(GITHUB_REPO_PATH):
                if file.endswith(".m3u"):
                    os.rename(os.path.join(GITHUB_REPO_PATH, file), M3U_PATH)
                    break
            if not os.path.exists(M3U_PATH):
                raise Exception("M3U文件下载失败")
        print(f"✅ M3U源文件已下载：{M3U_PATH}")

        # 9. 上传到GitHub
        print(f"【步骤7】上传到GitHub")
        github_link = upload_m3u_to_github()

        # 最终结果
        print(f"\n【完成】=====")
        print(f"  目标获取：第 {TARGET_IP_RANK} 新的有效组播IP")
        print(f"  选中IP：{target_ip}")
        print(f"  M3U文件路径：{M3U_PATH}")
        print(f"  GitHub订阅链接：{github_link}")

    except Exception as e:
        print(f"\n❌ 流程出错：{str(e)}")
    finally:
        if driver:
            driver.quit()
        if github_link:
            print(f"\n【订阅链接】{github_link}")


if __name__ == "__main__":
    try:
        kw = input(f"请输入搜索关键词（回车=默认：{DEFAULT_SEARCH_KEYWORD}）：").strip()
        rk = input(f"请输入第几个新的IP（回车=默认：{DEFAULT_TARGET_IP_RANK}）：").strip()

        SEARCH_KEYWORD = kw if kw else DEFAULT_SEARCH_KEYWORD
        TARGET_IP_RANK = int(rk) if rk.isdigit() else DEFAULT_TARGET_IP_RANK

    except Exception:
        SEARCH_KEYWORD = DEFAULT_SEARCH_KEYWORD
        TARGET_IP_RANK = DEFAULT_TARGET_IP_RANK

    print(f"\n【当前配置】关键词={SEARCH_KEYWORD}，第{TARGET_IP_RANK}新IP\n")

    extract_m3u()

