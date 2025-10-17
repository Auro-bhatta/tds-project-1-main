from fastapi import FastAPI, Request
import os, json
from dotenv import load_dotenv
from app.llm_generator import generate_app_code, decode_attachments
from app.github_utils import create_repo, get_repo, create_or_update_file, enable_pages
from app.notify import notify_evaluation_server

load_dotenv()
USER_SECRET = os.getenv("USER_SECRET")
USERNAME = os.getenv("GITHUB_USERNAME")
PROCESSED_PATH = "/tmp/processed_requests.json"

app = FastAPI()

def load_processed():
    if os.path.exists(PROCESSED_PATH):
        try:
            return json.load(open(PROCESSED_PATH))
        except json.JSONDecodeError:
            return {}
    return {}

def save_processed(data):
    json.dump(data, open(PROCESSED_PATH, "w"), indent=2)

def generate_mit_license():
    """Generate MIT License text"""
    from datetime import datetime
    year = datetime.now().year
    return f"""MIT License

Copyright (c) {year}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE."""

# === Main endpoint ===
@app.post("/ready")
async def receive_request(request: Request):
    data = await request.json()
    print("📩 Received request:", data)
    if data.get("secret") != USER_SECRET:
        print("❌ Invalid secret received.")
        return {"error": "Invalid secret"}

    processed = load_processed()
    key = f"{data['email']}::{data['task']}::round{data.get('round', 1)}::nonce{data['nonce']}"

    if key in processed:
        print(f"⚠️ Duplicate request detected for {key}. Re-notifying only.")
        prev = processed[key]
        try:
            notify_evaluation_server(
                data.get("evaluation_url"),
                prev["email"],
                prev["task"],
                prev["round"],
                prev["nonce"],
                prev["repo_url"],
                prev["commit_sha"],
                prev["pages_url"]
            )
            print("✅ Re-notification sent")
        except Exception as e:
            print(f"⚠️ Re-notification failed: {e}")
        return {"status": "ok", "note": "duplicate handled & re-notified"}

    try:
        round_num = data.get("round", 1)
        task_id = data["task"]
        
        print(f"🚀 Processing task: {task_id}, round {round_num}")
        attachments = data.get("attachments", [])
        saved_attachments = decode_attachments(attachments)
        print(f"📎 Attachments saved: {len(saved_attachments)}")
        
        # Get previous README if Round 2
        prev_readme = None
        if round_num == 2:
            try:
                repo = get_repo(task_id)
                prev_readme_file = repo.get_contents("README.md")
                prev_readme = prev_readme_file.decoded_content.decode("utf-8")
                print(f"📖 Retrieved previous README for round 2")
            except Exception as e:
                print(f"⚠️ Could not get previous README: {e}")
        
        # Generate files using LLM
        print("🤖 Generating code with AI...")
        gen = generate_app_code(
            data["brief"],
            attachments=attachments,
            checks=data.get("checks", []),
            round_num=round_num,
            prev_readme=prev_readme
        )
        
        files = gen.get("files", {})
        print(f"✅ Generated {len(files)} files: {list(files.keys())}")
        
        # Create or get repository
        try:
            repo = create_repo(task_id, description=f"Auto-generated: {data['brief']}")
            print(f"✅ Repository created: {task_id}")
        except Exception as e:
            print(f"⚠️ Repository exists, fetching: {e}")
            repo = get_repo(task_id)
        
        # Commit files
        print(f"📝 Committing {len(files)} files...")
        
        # Commit index.html
        if "index.html" in files:
            try:
                create_or_update_file(
                    repo, 
                    "index.html", 
                    files["index.html"], 
                    f"Round {round_num}: Add/Update index.html"
                )
                print("   ✅ index.html committed")
            except Exception as e:
                print(f"   ❌ Failed to commit index.html: {e}")
        else:
            print("   ⚠️ No index.html generated!")
        
        # Commit README.md
        if "README.md" in files:
            try:
                create_or_update_file(
                    repo, 
                    "README.md", 
                    files["README.md"], 
                    f"Round {round_num}: Add/Update README.md"
                )
                print("   ✅ README.md committed")
            except Exception as e:
                print(f"   ❌ Failed to commit README.md: {e}")
        else:
            print("   ⚠️ No README.md generated!")
        
        # Commit LICENSE
        if "LICENSE" in files:
            license_content = files["LICENSE"]
        else:
            license_content = generate_mit_license()
        
        try:
            create_or_update_file(repo, "LICENSE", license_content, f"Round {round_num}: Add/Update LICENSE")
            print("   ✅ LICENSE committed")
        except Exception as e:
            print(f"   ❌ Failed to commit LICENSE: {e}")
        
        # Enable GitHub Pages
        try:
            enable_pages(repo, branch="main")
            print("✅ GitHub Pages enabled")
        except Exception as e:
            print(f"⚠️ GitHub Pages error: {e}")
        
        # Get URLs
        repo_url = f"https://github.com/{USERNAME}/{task_id}"
        pages_url = f"https://{USERNAME}.github.io/{task_id}/"
        commit_sha = repo.get_branch("main").commit.sha
        
        print("\n" + "=" * 70)
        print(f"✅ Task {task_id} completed!")
        print(f"📦 Repo: {repo_url}")
        print(f"🌐 Live: {pages_url}")
        print(f"📝 Commit: {commit_sha}")
        print("=" * 70 + "\n")
        
        # Notify evaluation server
        try:
            notify_evaluation_server(
                data.get("evaluation_url"),
                data.get("email"),
                task_id,
                round_num,
                data.get("nonce"),
                repo_url,
                commit_sha,
                pages_url
            )
            print("✅ Evaluation server notified")
        except Exception as e:
            print(f"⚠️ Notification failed: {e}")
        
        # Save to processed cache
        processed[key] = {
            "email": data.get("email"),
            "task": task_id,
            "round": round_num,
            "nonce": data.get("nonce"),
            "repo_url": repo_url,
            "commit_sha": commit_sha,
            "pages_url": pages_url
        }
        save_processed(processed)
        
        # Return success response
        return {
            "status": "success",
            "task": task_id,
            "round": round_num,
            "repo_url": repo_url,
            "pages_url": pages_url,
            "commit_sha": commit_sha,
            "message": f"Task {task_id} round {round_num} completed successfully"
        }
        
    except Exception as e:
        print(f"❌ Error processing task: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "message": str(e),
            "task": data.get("task", "unknown")
        }

@app.get("/")
async def health_check():
    return {
        "service": "TDS Code Generator",
        "status": "running",
        "endpoints": {
            "ready": "POST /ready"
        }
    }
