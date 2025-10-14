"""
LLM Generator Module
Uses Google Gemini API to generate web application code
"""

import os
from google import genai
from pathlib import Path

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

TMP_DIR = Path("/tmp/llm_attachments")
TMP_DIR.mkdir(parents=True, exist_ok=True)


def decode_attachments(attachments):
    """
    Decode and save base64 attachments
    attachments: list of {name, url: data:<mime>;base64,<b64>}
    Saves files into /tmp/llm_attachments/<name>
    Returns list of dicts: {"name": name, "path": "/tmp/..", "mime": mime, "size": n}
    """
    import base64
    
    saved = []
    for att in attachments or []:
        name = att.get("name") or "attachment"
        url = att.get("url", "")
        if not url.startswith("data:"):
            continue
        try:
            header, b64data = url.split(",", 1)
            mime = header.split(";")[0].replace("data:", "")
            data = base64.b64decode(b64data)
            path = TMP_DIR / name
            with open(path, "wb") as f:
                f.write(data)
            saved.append({
                "name": name,
                "path": str(path),
                "mime": mime,
                "size": len(data)
            })
        except Exception as e:
            print(f"Failed to decode attachment {name}: {e}")
    return saved


def summarize_attachment_meta(saved):
    """
    saved is list from decode_attachments.
    Returns a short human-readable summary string for the prompt.
    """
    if not saved:
        return ""
    summaries = []
    for att in saved:
        summaries.append(f"  - {att['name']} ({att['mime']}, {att['size']} bytes)")
    return "\n".join(summaries)


def generate_app_code(brief, attachments=None, checks=None, round_num=1, prev_readme=None):
    """
    Generate or revise web application code using Gemini API
    
    Args:
        brief: Description of what to build
        attachments: List of file attachments (base64 encoded)
        checks: List of requirements/checks to satisfy
        round_num: Round number (1 or 2)
        prev_readme: Previous README content (for Round 2 revisions)
    
    Returns:
        dict: {
            "files": {"index.html": code, "README.md": readme},
            "attachments": saved_attachments
        }
    """
    # Handle attachments
    saved = decode_attachments(attachments or [])
    attachments_meta = summarize_attachment_meta(saved)
    
    # Build context for Round 2
    context_note = ""
    if round_num == 2 and prev_readme:
        context_note = f"\n### Previous README.md:\n{prev_readme}\n\nRevise and enhance this project according to the new brief below.\n"
    
    # Build user prompt
    user_prompt = f"""You are a professional web developer assistant.

### Round
{round_num}

### Task
{brief}
"""
    
    if context_note:
        user_prompt += context_note
    
    if checks:
        user_prompt += f"\n### Checks to Satisfy\n" + "\n".join(f"- {c}" for c in checks)
    
    if attachments_meta:
        user_prompt += f"\n### Attachments Provided\n{attachments_meta}"
    
    # Generate code using Gemini
    try:
        if not GEMINI_API_KEY:
            raise Exception("GEMINI_API_KEY not found in environment")
        
        # Use new Gemini SDK format
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # Create enhanced prompt
        content = f"""{user_prompt}

Generate complete, production-ready code.

Requirements:
- Create a single, self-contained HTML file with embedded CSS and JavaScript
- Modern, professional design with clean UI/UX
- Fully responsive (mobile-first approach)
- Use semantic HTML5 elements
- Professional color scheme and typography
- Include all necessary styling inline in <style> tags
- Include all JavaScript inline in <script> tags
- No external dependencies (no CDN links)

IMPORTANT OUTPUT FORMAT:
1. First, output the complete HTML code
2. Then add a separator line: ---README.md---
3. Then output a detailed README.md with:
   - Project description
   - Features
   - How to use
   - Technologies used

Start HTML directly with <!DOCTYPE html>.
"""
        
        # Generate content using new SDK
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=content
        )
        
        text = response.text or ""
        
        # Clean up markdown code blocks
        text = text.strip()
        
        # Remove markdown code block markers
        if "html" in text[:20]:
            text = text.replace(chr(96)*3 + "html", "", 1)
        
        text = text.replace(chr(96)*3, "")
        text = text.strip()
        
        print("✅ Generated code using Gemini API.")
        
    except Exception as e:
        print(f"⚠️ Gemini API failed: {e}, using fallback HTML instead")
        text = f"""{generate_fallback_html(brief)}---README.md---
{generate_readme_fallback(brief, checks, attachments_meta, round_num)}"""
    
    # Split code and README
    if "---README.md---" in text:
        code_part, readme_part = text.split("---README.md---", 1)
        code_part = _strip_code_block(code_part)
        readme_part = _strip_code_block(readme_part)
    else:
        code_part = _strip_code_block(text)
        readme_part = generate_readme_fallback(brief, checks, attachments_meta, round_num)
    
    files = {"index.html": code_part, "README.md": readme_part}
    return {"files": files, "attachments": saved}


def generate_fallback_html(brief):
    """Generate simple fallback HTML when API fails"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Generated App</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        
        .container {{
            background: rgba(255, 255, 255, 0.95);
            border-radius: 20px;
            padding: 40px;
            max-width: 800px;
            width: 100%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            animation: fadeIn 0.5s ease-in;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(20px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        h1 {{
            color: #667eea;
            margin-bottom: 20px;
            font-size: 2.5em;
        }}
        
        p {{
            color: #333;
            line-height: 1.6;
            margin-bottom: 15px;
        }}
        
        .info {{
            background: #f0f0f0;
            padding: 20px;
            border-radius: 10px;
            margin-top: 20px;
            border-left: 4px solid #667eea;
        }}
        
        .info strong {{
            color: #764ba2;
        }}
        
        @media (max-width: 600px) {{
            .container {{
                padding: 20px;
            }}
            
            h1 {{
                font-size: 1.8em;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 Generated App</h1>
        <p>This application was generated using LLM technology.</p>
        <p>The system successfully processed your request and created this responsive web application.</p>
        <div class="info">
            <strong>Brief:</strong> {brief}
        </div>
    </div>
</body>
</html>"""


def generate_readme_fallback(brief, checks, attachments_meta, round_num):
    """Generate README.md content"""
    content = f"""# Generated Web Application

## Brief
{brief}

## Round
Round {round_num}

"""
    
    if checks:
        content += "## Requirements\n"
        for check in checks:
            content += f"- {check}\n"
        content += "\n"
    
    if attachments_meta:
        content += "## Attachments\n{}\n\n".format(attachments_meta)
    
    content += """## Usage
Open `index.html` in a web browser to view the application.

## Technologies
- HTML5
- CSS3
- JavaScript

---
*Generated using LLM Code Generator*
"""
    
    return content


def _strip_code_block(text):
    """Remove markdown code block markers"""
    text = text.strip()
    
    # Use chr(96) to avoid syntax errors with backticks
    backtick = chr(96)
    triple_backtick = backtick * 3
    
    # Remove code block markers
    text = text.replace(triple_backtick + "html", "")
    text = text.replace(triple_backtick + "markdown", "")
    text = text.replace(triple_backtick, "")
    
    return text.strip()
