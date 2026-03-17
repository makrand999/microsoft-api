import json
import asyncio
import aiohttp
import sys
from pathlib import Path

# Limit concurrent requests to avoid being banned/rate-limited
CONCURRENCY_LIMIT = 10
semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

def load_cookies(path="session.json"):
    if not Path(path).exists():
        print(f"[!] '{path}' not found.")
        sys.exit(1)
    with open(path, "r") as f:
        raw = json.load(f)
    return {c["name"]: c["value"] for c in raw}

async def mark_complete(session, url, payload, title):
    """Generic wrapper for async POST requests"""
    async with semaphore:
        try:
            async with session.post(url, json=payload) as resp:
                status = resp.status
                # Sync CSRF from response cookies if provided
                if "csrf_token" in resp.cookies:
                    session.headers.update({"Csrf-Token": resp.cookies["csrf_token"].value})
                print(f"  [✓] {status} | {title}")
                return status
        except Exception as e:
            print(f"  [!] Failed {title}: {e}")
            return None

async def main():
    cookies = load_cookies()
    initial_csrf = cookies.get("csrf_token")
    
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "Origin": "https://www.freecodecamp.org",
        "Referer": "https://www.freecodecamp.org/",
        "Csrf-Token": initial_csrf,
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
    }

    async with aiohttp.ClientSession(headers=headers, cookies=cookies) as session:
        # 1. Fetch Challenges
        print("[*] Fetching challenge list...")
        list_url = "https://www.freecodecamp.org/page-data/learn/foundational-c-sharp-with-microsoft/page-data.json"
        async with session.get(list_url) as resp:
            data = await resp.json()
            nodes = data["result"]["data"]["allChallengeNode"]["nodes"]
            challenges = [n["challenge"] for n in nodes if n["challenge"]["superBlock"] == "foundational-c-sharp-with-microsoft"]

        print(f"[*] Found {len(challenges)} challenges. Processing...")

        tasks = []
        exam_challenge = None

        # 2. Queue up tasks
        for ch in challenges:
            cid, ctype, title = ch["id"], ch["challengeType"], ch["title"]

            if ctype == 17:
                exam_challenge = ch
                continue

            if ctype == 18:
                url = "https://api.freecodecamp.org/ms-trophy-challenge-completed"
                payload = {"id": cid, "challengeType": 18}
            else:
                url = "https://api.freecodecamp.org/encoded/modern-challenge-completed"
                payload = {"id": cid, "challengeType": ctype}
            
            tasks.append(mark_complete(session, url, payload, title))

        # Run challenge completions in parallel
        await asyncio.gather(*tasks)

        # 3. Handle Exam last (to ensure requirements are met)
        if exam_challenge:
            print(f"\n[*] Submitting exam: {exam_challenge['title']}")
            # Exam payload logic
            ans = [{"id": "8fyuxnv4ya", "question": "...", "answer": {"id": "qel6n5v3ma", "answer": "`break;`"}}] * 80
            payload = {
                "id": exam_challenge["id"],
                "challengeType": 17,
                "userCompletedExam": {"userExamQuestions": ans, "examTimeInSeconds": 300}
            }
            await mark_complete(session, "https://api.freecodecamp.org/exam-challenge-completed", payload, "FINAL EXAM")

    print("\n[✓] All operations completed.")

if __name__ == "__main__":
    asyncio.run(main())