import requests
import os
from dotenv import load_dotenv
import time

load_dotenv()

def notify_evaluation_server(evaluation_url: str, email: str, task_id: str, round_num: int, nonce: str, repo_url: str, commit_sha: str, pages_url: str) -> bool:
    """
    Send repo details back to the evaluation server.
    Retries with exponential backoff if needed.
    """
    
    payload = {
        "email": email,
        "task": task_id,
        "round": round_num,
        "nonce": nonce,
        "repo_url": repo_url,
        "commit_sha": commit_sha,
        "pages_url": pages_url
    }
    
    headers = {"Content-Type": "application/json"}
    delay = 1  # start with 1 second
    
    for attempt in range(5):  # try up to 5 times
        try:
            r = requests.post(evaluation_url, headers=headers, json=payload, timeout=30)
            
            if r.status_code == 200:
                print(f"✅ Evaluation server notified successfully.")
                return True
            else:
                print(f"⚠️ Attempt {attempt+1}: Server responded {r.status_code} - {r.text}")
                
        except Exception as e:
            print(f"❌ Attempt {attempt+1} failed: {e}")
        
        # Exponential backoff
        if attempt < 4:
            time.sleep(delay)
            delay *= 2
    
    print(f"❌ Failed to notify evaluation server after retries.")
    return False
