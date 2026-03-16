"""
Microsoft Learn - Automatic Course Completion Script
=====================================================
Completes units in the C# learning path (all 6 parts).
Answers all quiz questions with option index 0 (first option).

Usage:
    1. Place your cookies in settings.json (same directory)
    2. Run: python ms_learn_autocomplete.py

settings.json format: The cookie JSON array exported from your browser.
"""

import json
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# ─── Config ────────────────────────────────────────────────────────────────────

BASE_URL   = "https://learn.microsoft.com"
LOCALE     = "en-us"
LOCALE_GB  = "en-gb"

LEARNING_PATHS = [
    "learn.wwl.get-started-c-sharp-part-1",
    "learn.wwl.get-started-c-sharp-part-2",
    "learn.wwl.get-started-c-sharp-part-3",
    "learn.wwl.get-started-c-sharp-part-4",
    "learn.wwl.get-started-c-sharp-part-5",
    "learn.wwl.get-started-c-sharp-part-6",
]

SETTINGS_FILE = Path(__file__).parent / "settings.json"

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.9",
    "content-type": "application/json",
    "origin": "https://learn.microsoft.com",
    "referer": "https://learn.microsoft.com/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
}

IMPORTANT_COOKIES = {"DocsToken", "ai_session", "MS0", "MUID", "MC1", "MSFPC", "mbox"}

# ─── Cookie helpers ────────────────────────────────────────────────────────────

def load_cookies(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        cookie_list = json.load(f)
    return {c["name"]: c["value"] for c in cookie_list}


def save_cookies(session: requests.Session, path: Path) -> None:
    """Merge updated important cookies back into settings.json (called once at end)."""
    with open(path, "r", encoding="utf-8") as f:
        original_list: list[dict] = json.load(f)

    session_cookies = {c.name: c.value for c in session.cookies}
    updated = []

    for cookie_obj in original_list:
        name = cookie_obj["name"]
        if name in IMPORTANT_COOKIES and name in session_cookies:
            if cookie_obj["value"] != session_cookies[name]:
                print(f"  [cookies] Updated: {name}")
                cookie_obj["value"] = session_cookies[name]
        updated.append(cookie_obj)

    existing_names = {c["name"] for c in original_list}
    for name, value in session_cookies.items():
        if name in IMPORTANT_COOKIES and name not in existing_names:
            print(f"  [cookies] New cookie saved: {name}")
            updated.append({
                "domain": "learn.microsoft.com",
                "hostOnly": True, "httpOnly": False,
                "name": name, "path": "/",
                "sameSite": "no_restriction", "secure": True,
                "session": False, "storeId": "0", "value": value,
            })

    with open(path, "w", encoding="utf-8") as f:
        json.dump(updated, f, indent=2)


class PersistentSession(requests.Session):
    def __init__(self, cookie_path: Path):
        super().__init__()
        self.cookie_path = cookie_path


# ─── API helpers ───────────────────────────────────────────────────────────────

def get_path_modules(session: requests.Session, path_uid: str) -> list:
    url = f"{BASE_URL}/api/hierarchy/paths/{path_uid}"
    print(f"  [debug] GET {url}")
    resp = session.get(url, params={"locale": LOCALE_GB})
    print(f"  [debug] Response status: {resp.status_code}")
    resp.raise_for_status()
    modules = resp.json().get("modules", [])
    print(f"  [debug] Modules found: {len(modules)}")
    return modules


def get_module_units(session: requests.Session, module_uid: str) -> list:
    url = f"{BASE_URL}/api/hierarchy/modules/{module_uid}"
    print(f"  [debug] GET {url}")
    resp = session.get(url, params={"locale": LOCALE_GB})
    print(f"  [debug] Response status: {resp.status_code}")
    resp.raise_for_status()
    units = resp.json().get("units", [])
    print(f"  [debug] Units found in module: {len(units)}")
    return units


def count_quiz_questions(session: requests.Session, unit_url: str) -> int:
    """Count divs with class="quiz-question" in the unit HTML.

    Must use locale-prefixed URL (/en-us/training/...) and browser-like
    navigation headers — otherwise MS Learn returns a minimal shell page
    without the quiz content.
    """
    # unit_url is like /training/modules/.../5-knowledge-check/
    # browser always requests /en-gb/training/... with navigation headers
    full_url = f"{BASE_URL}/en-us{unit_url}"
    page_headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "upgrade-insecure-requests": "1",
    }
    print(f"    [debug] Fetching unit page: {full_url}")
    try:
        resp = session.get(full_url, headers=page_headers, timeout=15)
    except Exception as e:
        print(f"    [debug] Page fetch failed: {e}")
        return 0
    print(f"    [debug] Page status: {resp.status_code}  |  HTML size: {len(resp.text)} bytes")
    if resp.status_code != 200:
        return 0
    count = resp.text.count('class="quiz-question"')
    print(f'    [debug] class="quiz-question" occurrences: {count}')
    return count


def extract_correct_answers(details: list) -> list[dict] | None:
    """
    Parse the 'details' array from a quiz PUT response and build a corrected
    answers payload. Returns None if details is empty or all were correct.

    Each detail looks like:
      {"id": 0, "isCorrect": false, "choices": [{"id": 0, "isCorrect": false}, {"id": 2, "isCorrect": true}]}

    We pick the choice with isCorrect=true for each question.
    """
    if not details:
        return None

    corrected = []
    all_correct = True
    for q in details:
        q_id = str(q.get("id", 0))
        correct_choices = [str(c["id"]) for c in q.get("choices", []) if c.get("isCorrect")]
        if not correct_choices:
            # No correct choice info — keep "0" as fallback
            correct_choices = ["0"]
        corrected.append({"id": q_id, "answers": correct_choices})
        if not q.get("isCorrect"):
            all_correct = False

    if all_correct:
        print(f"    [debug] All answers were correct on first attempt — no resubmit needed")
        return None

    return corrected  # list of {"id": str, "answers": [str]}


def mark_unit_complete(session: requests.Session, unit_uid: str, num_questions: int = 0, unit_url: str = "") -> dict:
    url         = f"{BASE_URL}/api/progress/units/{unit_uid}/"
    params      = {"locale": LOCALE}
    req_headers = {"referer": BASE_URL + unit_url} if unit_url else {}

    print(f"    [debug] PUT {url}")

    # ── Reading unit — no questions, single PUT with no body ──────────────────
    if num_questions == 0:
        print(f"    [debug] No questions — single PUT (reading unit)")
        resp = session.put(url, params=params, headers=req_headers)
        print(f"    [debug] Response: {resp.status_code}  body: {resp.text[:200]}")
        return {"status": resp.status_code, "body": resp.text[:200]}

    # ── Quiz unit — attempt 1: all answers "0" ────────────────────────────────
    payload = [{"id": str(i), "answers": ["0"]} for i in range(num_questions)]
    print(f"    [debug] Questions: {num_questions}  |  Attempt 1 payload: {json.dumps(payload)}")
    resp = session.put(url, params=params, json=payload, headers=req_headers)
    print(f"    [debug] Attempt 1 response: {resp.status_code}  body: {resp.text[:300]}")

    if resp.status_code != 200:
        return {"status": resp.status_code, "body": resp.text[:200]}

    try:
        data = resp.json()
    except Exception as e:
        print(f"    [debug] Failed to parse JSON response: {e}")
        return {"status": resp.status_code, "body": resp.text[:200]}

    updated = data.get("updated", False)
    passed  = data.get("passed", False)
    details = data.get("details", [])
    print(f"    [debug] Attempt 1 result: updated={updated}  passed={passed}  details_count={len(details)}")

    # ── Attempt 2: resubmit with correct answers extracted from details ────────
    corrected = extract_correct_answers(details)
    if corrected is None:
        return {"status": resp.status_code, "body": resp.text[:200]}

    print(f"    [debug] Attempt 2 payload (corrected): {json.dumps(corrected)}")
    resp2 = session.put(url, params=params, json=corrected, headers=req_headers)
    print(f"    [debug] Attempt 2 response: {resp2.status_code}  body: {resp2.text[:300]}")

    try:
        data2 = resp2.json()
        print(f"    [debug] Attempt 2 result: updated={data2.get('updated')}  passed={data2.get('passed')}")
    except Exception:
        pass

    return {"status": resp2.status_code, "body": resp2.text[:200]}


# ─── Unit / module / path runners ──────────────────────────────────────────────

def process_unit(session: requests.Session, unit: dict) -> None:
    unit_uid   = unit.get("uid", "")
    unit_title = unit.get("title", unit_uid)
    unit_url   = unit.get("url", "")
    is_assess  = unit.get("module_assessment", False)
    tag        = "[QUIZ]" if is_assess else "      "

    print(f"\n  │  ── Processing: {unit_title}")
    print(f"    [debug] UID: {unit_uid}")
    print(f"    [debug] URL: {unit_url}")
    print(f"    [debug] module_assessment flag: {is_assess}")
    print(f"    [debug] All unit keys: {list(unit.keys())}  type={unit.get('type')}  title={unit_title}")

    # Units with points == 100 are plain reading/intro/summary units — never have questions.
    # Units with points > 100 (200) may have inline quiz questions or are module assessments.
    # This avoids a page GET for every low-value unit, cutting requests roughly in half.
    unit_points = unit.get("points", 0)
    print(f"    [debug] points={unit_points} — {'fetching page to count questions' if unit_points > 100 else 'skipping page fetch (reading unit)'}")

    num_q = 0
    if unit_url and unit_points > 100:
        try:
            num_q = count_quiz_questions(session, unit_url)
        except Exception as e:
            print(f"    [debug] count_quiz_questions raised: {e}")

    result      = mark_unit_complete(session, unit_uid, num_q, unit_url)
    status      = result["status"]
    status_icon = "✓" if status in (200, 201, 204) else f"✗ ({status})"
    q_info      = f"  [{num_q} Q]" if num_q > 0 else ""
    print(f"  │  {status_icon} {tag} {unit_title}{q_info}")


def complete_module(session: requests.Session, module: dict) -> None:
    module_uid   = module.get("uid", "")
    module_title = module.get("title", module_uid)
    print(f"\n  ┌─ Module: {module_title}")
    print(f"  [debug] Module UID: {module_uid}")

    units = module.get("units", [])
    if not units:
        try:
            units = get_module_units(session, module_uid)
        except Exception as e:
            print(f"  │  [ERROR] Could not fetch units: {e}")
            return

    print(f"  [debug] Total units to process: {len(units)}")

    with ThreadPoolExecutor(max_workers=len(units)) as executor:
        futures = {executor.submit(process_unit, session, unit): unit for unit in units}
        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                unit = futures[future]
                print(f"  │  ✗ [ERROR] {unit.get('title', '?')}: {e}")

    print(f"  └─ Module done\n")


def complete_path(session: requests.Session, path_uid: str) -> None:
    print(f"\n{'='*60}")
    print(f"  Learning Path: {path_uid}")
    print(f"{'='*60}")
    try:
        modules = get_path_modules(session, path_uid)
    except Exception as e:
        print(f"  [ERROR] Could not fetch path: {e}")
        return
    for module in modules:
        complete_module(session, module)


# ─── Menu helpers ──────────────────────────────────────────────────────────────

def pick(options: list, prompt: str) -> int:
    """Print a numbered list and return chosen 0-based index."""
    for i, label in enumerate(options):
        print(f"  [{i}] {label}")
    while True:
        raw = input(f"\n{prompt} (0-{len(options)-1}): ").strip()
        if raw.isdigit() and 0 <= int(raw) < len(options):
            return int(raw)
        print("  Invalid choice, try again.")


def select_path_and_modules(session: requests.Session):
    """Returns (path_uid, modules) after user picks a path."""
    print("\n── Select Learning Path ──")
    idx      = pick(LEARNING_PATHS, "Choose path")
    path_uid = LEARNING_PATHS[idx]
    print(f"\n  Fetching modules for {path_uid} ...")
    modules  = get_path_modules(session, path_uid)
    return path_uid, modules


def select_module_and_units(session: requests.Session):
    """Returns (module, units) after user picks path → module."""
    _, modules = select_path_and_modules(session)
    print("\n── Select Module ──")
    idx    = pick([m.get("title", m.get("uid")) for m in modules], "Choose module")
    module = modules[idx]
    units  = module.get("units", [])
    if not units:
        units = get_module_units(session, module.get("uid", ""))
    return module, units


# ─── Menu actions ──────────────────────────────────────────────────────────────

def menu_specific_path(session: requests.Session) -> None:
    _, modules = select_path_and_modules(session)
    # re-wrap into a fake path structure isn't needed — just iterate modules
    for module in modules:
        complete_module(session, module)


def menu_specific_module(session: requests.Session) -> None:
    module, _ = select_module_and_units(session)
    complete_module(session, module)


def menu_single_unit(session: requests.Session) -> None:
    module, units = select_module_and_units(session)
    print("\n── Select Unit ──")
    idx  = pick([u.get("title", u.get("uid")) for u in units], "Choose unit")
    unit = units[idx]
    print()
    process_unit(session, unit)
    print("\n✓ Unit processed.")


def show_main_menu() -> str:
    print("\n" + "═"*50)
    print("  Microsoft Learn — C# Auto-Completer")
    print("═"*50)
    print("  [1] Complete ALL paths (parts 1–6)")
    print("  [2] Complete a specific PATH")
    print("  [3] Complete a specific MODULE")
    print("  [4] Complete a specific UNIT")
    print("  [0] Exit")
    return input("\nChoice: ").strip()


# ─── Entry point ───────────────────────────────────────────────────────────────

def main():
    print("Microsoft Learn — C# Course Auto-Completer")
    print("─" * 45)

    if not SETTINGS_FILE.exists():
        print(f"\n[ERROR] settings.json not found at: {SETTINGS_FILE}")
        print("Please place your browser-exported cookie JSON there and retry.")
        return

    cookies = load_cookies(SETTINGS_FILE)
    print(f"Loaded {len(cookies)} cookies from settings.json")

    session = PersistentSession(SETTINGS_FILE)
    session.cookies.update(cookies)
    session.headers.update(HEADERS)

    # The API requires DocsToken as a Bearer token in Authorization header
    # Using only cookies results in "updated": false — the Bearer header is what
    # actually marks progress as updated on the server side
    docs_token = cookies.get("DocsToken", "")
    if docs_token:
        session.headers["authorization"] = f"Bearer {docs_token}"
        print(f"[debug] Authorization Bearer header set (token length: {len(docs_token)})")
    else:
        print("[WARN] DocsToken not found in cookies — progress may not be marked")

    print("[debug] Checking auth ...")
    test = session.get(f"{BASE_URL}/api/profile", params={"locale": LOCALE})
    print(f"[debug] /api/profile status: {test.status_code}")
    if test.status_code == 401:
        print("\n[ERROR] Authentication failed — DocsToken may have expired.")
        print("Re-export cookies from your browser after logging in.")
        return
    print("Auth check passed ✓")

    try:
        while True:
            choice = show_main_menu()
            if choice == "1":
                for path_uid in LEARNING_PATHS:
                    complete_path(session, path_uid)
                    time.sleep(1)
                print("\n🎉  All 6 parts completed.")
            elif choice == "2":
                menu_specific_path(session)
            elif choice == "3":
                menu_specific_module(session)
            elif choice == "4":
                menu_single_unit(session)
            elif choice == "0":
                break
            else:
                print("  Invalid choice.")
    finally:
        print("\nSaving updated cookies...")
        save_cookies(session, SETTINGS_FILE)
        print("Cookies saved. Bye!")


if __name__ == "__main__":
    main()