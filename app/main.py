
from fastapi import FastAPI, Request, BackgroundTasks
import os, json
from dotenv import load_dotenv
from app.llm_generator import generate_app_code, decode_attachments, generate_license
from app.github_utils import create_repo, get_repo, create_or_update_file, enable_pages
from app.notify import notify_evaluation_server

load_dotenv()
USER_SECRET = os.getenv("USER_SECRET")
USERNAME = os.getenv("GITHUB_USERNAME")
PROCESSED_PATH = "/tmp/processed_requests.json"

app = FastAPI()

# === Persistence for processed requests ===
def load_processed():
    if os.path.exists(PROCESSED_PATH):
        try:
            return json.load(open(PROCESSED_PATH))
        except json.JSONDecodeError:
            return {}
    return {}

def save_processed(data):
    json.dump(data, open(PROCESSED_PATH, "w"), indent=2)

# === Background task ===
def process_request(data):
    """Background task to process request"""
    round_num = data.get("round", 1)
    task_id = data["task"]
    
    print(f"⚙️  Starting background process for task {task_id}, round {round_num}")
    
    # Decode attachments
    attachments = data.get("attachments", [])
    saved_attachments = decode_attachments(attachments)
    print(f"Attachments saved: {saved_attachments}")
    
    # Get previous README if Round 2
    prev_readme = None
    if round_num == 2:
        try:
            repo = get_repo(task_id)
            prev_readme_file = repo.get_contents("README.md")
            prev_readme = prev_readme_file.decoded_content.decode("utf-8")
            print(f"📖 Retrieved previous README for round 2")
        except Exception as e:
            print(f"⚠️  Could not get previous README: {e}")
    
    # Generate files using LLM
    print(f"🤖 Generating code...")
    gen = generate_app_code(
        data["brief"],
        attachments=attachments,
        checks=data.get("checks", []),
        round_num=round_num,
        prev_readme=prev_readme
    )
    
    files = gen.get("files", {})
    
    # DEBUG: Print what was generated
    print(f"🔍 Generated files: {list(files.keys())}")
    for fname in files.keys():
        print(f"   - {fname}: {len(files[fname])} characters")
    
    # Create or get repository
        # Create or get repository
    from github import GithubException
        # Create or get repository
    repo = None
    try:
        # Truncate description to 100 characters max
        desc = f"Auto-generated app for task: {data['brief']}"
        if len(desc) > 100:
            desc = desc[:97] + "..."
        
        repo = create_repo(task_id, description=desc)
        print(f"✅ Repository created: {repo.name}")
    except Exception as e:
        error_str = str(e).lower()
        print(f"⚠️  Create failed: {str(e)[:200]}")
        
        # If repo already exists, get it
        if "already exists" in error_str or "422" in error_str:
            try:
                repo = get_repo(task_id)
                print(f"✅ Got existing repository: {repo.name}")
            except Exception as get_error:
                print(f"❌ Cannot get repository: {get_error}")
                raise get_error
        else:
            # Some other error
            print(f"❌ Repository creation failed with unexpected error")
            raise e
    
        # Commit ALL files FIRST (before trying to get branches)
    print(f"📝 Committing {len(files)} files...")
    
    # Commit index.html
    if "index.html" in files:
        try:
            create_or_update_file(
                repo, 
                "index.html", 
                files["index.html"], 
                f"Add/Update index.html for round {round_num}"
            )
            print("   ✅ index.html committed")
        except Exception as e:
            print(f"   ❌ Failed to commit index.html: {e}")
    
    # Commit README.md
    if "README.md" in files:
        try:
            create_or_update_file(
                repo, 
                "README.md", 
                files["README.md"], 
                f"Add/Update README.md for round {round_num}"
            )
            print("   ✅ README.md committed")
        except Exception as e:
            print(f"   ❌ Failed to commit README.md: {e}")
    
    # Commit LICENSE
    if "LICENSE" in files:
        try:
            create_or_update_file(repo, "LICENSE", files["LICENSE"], "Add/Update LICENSE")
            print("   ✅ LICENSE committed")
        except Exception as e:
            print(f"   ❌ Failed to commit LICENSE: {e}")
    
    # NOW get the branch and commit SHA (after files are committed)
    try:
        commit_sha = repo.get_branch("main").commit.sha
        print(f"✅ Got commit SHA: {commit_sha[:7]}")
    except Exception as e:
        print(f"⚠️  Could not get commit SHA: {e}")
        commit_sha = "unknown"
    
    # Enable GitHub Pages
    try:
        enable_pages(repo, branch="main")
        print("✅ GitHub Pages enabled")
    except Exception as e:
        print(f"⚠️  GitHub Pages error: {e}")
    
    # Get URLs
    repo_url = f"https://github.com/{USERNAME}/{task_id}"
    pages_url = f"https://{USERNAME}.github.io/{task_id}/"
    
    # Notify evaluation server
    try:
        notify_evaluation_server(
            data["evaluation_url"],
            data["email"],
            task_id,
            round_num,
            data["nonce"],
            repo_url,
            commit_sha,
            pages_url
        )
        print("✅ Evaluation server notified")
    except Exception as e:
        print(f"⚠️  Notification failed: {e}")
    
    print(f"✅ Task {task_id} completed!")
    print(f"   Repo: {repo_url}")
    print(f"   Live: {pages_url}")


# === Main endpoint ===
@app.post("/api-endpoint")
async def receive_request(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    print("📩 Received request:", data)

    # Step 0: Verify secret
    if data.get("secret") != USER_SECRET:
        print("❌ Invalid secret received.")
        return {"error": "Invalid secret"}

    processed = load_processed()
    key = f"{data['email']}::{data['task']}::round{data['round']}::nonce{data['nonce']}"

    # Duplicate detection
    if key in processed:
        print(f"⚠ Duplicate request detected for {key}. Re-notifying only.")
        prev = processed[key]
        notify_evaluation_server(data.get("evaluation_url"), prev)
        return {"status": "ok", "note": "duplicate handled & re-notified"}

    # Schedule background task (non-blocking)
    background_tasks.add_task(process_request, data)

    # Immediate HTTP 200 acknowledgment
    return {"status": "accepted", "note": f"processing round {data['round']} started"}

