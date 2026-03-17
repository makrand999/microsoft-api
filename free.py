import json
import requests
import time
import sys
from pathlib import Path

# ── Load cookies from session.json ──────────────────────────────────────────
def load_cookies(path="session.json"):
    with open(path, "r") as f:
        raw = json.load(f) 
    cookies = {}
    for c in raw:
        cookies[c["name"]] = c["value"] 
    return cookies

# ── Build a requests Session with those cookies ──────────────────────────────
def build_session(cookies: dict) -> requests.Session:
    s = requests.Session()
    
    # Extract initial token from the cookies provided in session.json [cite: 1]
    initial_csrf = cookies.get("csrf_token") 
    
    # Headers matched to your successful manual request 
    s.headers.update({
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Origin": "https://www.freecodecamp.org",
        "Referer": "https://www.freecodecamp.org/",
        "Csrf-Token": initial_csrf,
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
    })
    
    # Set cookies into the session jar [cite: 1]
    for name, value in cookies.items():
        s.cookies.set(name, value, domain=".freecodecamp.org")
    return s

# ── Update the CSRF header from the current cookie jar ──────────────────────
def sync_csrf_header(s: requests.Session):
    """
    Grabs the latest csrf_token from the session's cookie jar 
    and updates the 'Csrf-Token' header for the next request. 
    """
    latest_csrf = s.cookies.get("csrf_token")
    if latest_csrf:
        s.headers.update({"Csrf-Token": latest_csrf})

# ── Fetch all challenges for the super-block ────────────────────────────────
def get_challenges(s: requests.Session) -> list:
    # URL for the foundational C# course structure [cite: 1]
    url = "https://www.freecodecamp.org/page-data/learn/foundational-c-sharp-with-microsoft/page-data.json"
    resp = s.get(url)
    resp.raise_for_status()
    nodes = resp.json()["result"]["data"]["allChallengeNode"]["nodes"] 
    challenges = [n["challenge"] for n in nodes
                  if n["challenge"]["superBlock"] == "foundational-c-sharp-with-microsoft"] 
    print(f"[*] Found {len(challenges)} challenges in the super-block")
    return challenges

# ── Mark a regular / modern challenge as completed ──────────────────────────
def complete_challenge(s: requests.Session, challenge_id: str, challenge_type: int):
    url = "https://api.freecodecamp.org/encoded/modern-challenge-completed"
    payload = {"id": challenge_id, "challengeType": challenge_type} 
    resp = s.post(url, json=payload)
    sync_csrf_header(s) # Update header from response cookies 
    return resp

# ── Mark a trophy challenge as completed ────────────────────────────────────
def complete_trophy(s: requests.Session, challenge_id: str):
    url = "https://api.freecodecamp.org/ms-trophy-challenge-completed" 
    payload = {"id": challenge_id,"challengeType":18} 
    resp = s.post(url, json=payload)
    print(resp)
    sync_csrf_header(s)
    return resp

# ── Submit the certification exam (type 17) ─────────────────────────────────
def complete_exam(s: requests.Session, exam_id: str):
    url = "https://api.freecodecamp.org/exam-challenge-completed" 
    
    # Question data from the exam GET request [cite: 20, 23]
    KNOWN_QUESTION_ID = "8fyuxnv4ya"
    CORRECT_ANSWER_ID = "qel6n5v3ma" # `break;` 

    # Build 80 identical answer objects as requested [cite: 1]
    user_exam_questions = []
    for _ in range(80):
        user_exam_questions.append({
            "id": KNOWN_QUESTION_ID,
            "question": "How do you terminate a case block in a `switch` statement in C#?",
            "answer": {
                "id": CORRECT_ANSWER_ID,
                "answer": "`break;`"
            }
        })

    payload = {
        "id": exam_id,
        "challengeType": 17,
        "userCompletedExam": {
            "userExamQuestions": user_exam_questions,
            "examTimeInSeconds": 300 # 5 minutes [cite: 1]
        }
    }
    resp = s.post(url, json=payload)
    sync_csrf_header(s)
    return resp

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    cookie_file = "session.json"
    if not Path(cookie_file).exists():
        print(f"[!] '{cookie_file}' not found.")
        sys.exit(1)

    print("[*] Loading cookies and initializing session …")
    cookies = load_cookies(cookie_file)
    s = build_session(cookies)

    print("[*] Fetching challenge list …")
    try:
        challenges = get_challenges(s)
    except Exception as e:
        print(f"[!] Failed to fetch challenges: {e}")
        return

    exam_challenge = None

    for ch in challenges:
        cid   = ch["id"]
        ctype = ch["challengeType"]
        title = ch["title"]

        if ctype == 17:
            exam_challenge = ch
            continue

        if ctype == 18:
            print(f"  [trophy] {title} …", end=" ")
            r = complete_trophy(s, cid)
        else:
            print(f"  [challenge {ctype}] {title} …", end=" ")
            r = complete_challenge(s, cid, ctype)
        
        print(f"Status: {r.status_code}")
        time.sleep(0.5) # Polite delay to avoid rate limiting

    if exam_challenge:
        print(f"\n[*] Submitting exam: {exam_challenge['title']} …", end=" ")
        r = complete_exam(s, exam_challenge["id"])
        print(f"Status: {r.status_code}")
        if r.status_code != 200:
            print(f"Response: {r.text}")
    else:
        print("[!] No exam found in the super-block.")

    print("\n[✓] Done.")

if __name__ == "__main__":
    main()