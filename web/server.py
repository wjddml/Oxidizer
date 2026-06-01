"""
Oxidizer Web Server
Runs the full Oxidizer pipeline via HTTP API.
Start with: python server.py
"""

import os
import sys
import json
import tempfile
import threading
import uuid
from pathlib import Path
from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS

# Add src/ to path so imports work
SRC_DIR = Path(__file__).parent / "src"
sys.path.insert(0, str(SRC_DIR))

app = Flask(__name__, static_folder="web")
CORS(app)

PROJECT_ROOT = Path(__file__).parent
CONFIG_PATH  = str(PROJECT_ROOT / "config.yaml")

# ── Job store for streaming logs ──────────────────────────────
jobs: dict[str, dict] = {}   # job_id -> { logs:[], done:bool, result:str, error:str }


def emit(job_id: str, tag: str, tag_class: str, msg: str):
    """Append a log entry to the job's log queue."""
    jobs[job_id]["logs"].append({"tag": tag, "cls": tag_class, "msg": msg})


def run_pipeline_job(job_id: str, c_code: str, api_key: str):
    """Run the full Oxidizer pipeline in a background thread, emitting log events."""
    job = jobs[job_id]

    try:
        emit(job_id, "INIT",  "lt-init",  "Oxidizer pipeline started")

        # ── Override LLM to use Claude via Anthropic API ──────
        # We monkey-patch the LLM factory to use the user-supplied key
        os.environ["ANTHROPIC_API_KEY"] = api_key

        # Build a Claude client on the fly (mirrors llm_factory pattern)
        import anthropic

        class ClaudeClient:
            def __init__(self):
                self.client = anthropic.Anthropic(api_key=api_key)
                self.model  = "claude-sonnet-4-20250514"

            def generate(self, messages):
                emit(job_id, "LLM", "lt-llm",
                     f"Calling <b>{self.model}</b>...")
                sys_msg  = next((m["content"] for m in messages if m["role"] == "system"), None)
                user_msgs = [m for m in messages if m["role"] != "system"]

                kwargs = dict(
                    model=self.model,
                    max_tokens=4096,
                    messages=user_msgs,
                )
                if sys_msg:
                    kwargs["system"] = sys_msg

                resp = self.client.messages.create(**kwargs)
                text = resp.content[0].text.strip()

                # Strip markdown fences if present
                if text.startswith("```rust"):
                    text = text[7:]
                elif text.startswith("```"):
                    text = text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                return text.strip()

        # Patch factory so Orchestrator & RepairAgent both get our client
        import llm.llm_factory as _factory
        _real_create = _factory.create_llm_client
        _claude_instance = ClaudeClient()
        _factory.create_llm_client = lambda *a, **kw: _claude_instance

        # ── Phase 1: write C code to temp file ────────────────
        emit(job_id, "SETUP", "lt-phase", "Writing C source to workspace...")
        tmp_dir  = Path(tempfile.mkdtemp(prefix="oxidizer_web_"))
        c_file   = tmp_dir / "input.c"
        c_file.write_text(c_code, encoding="utf-8")

        # Patch data dirs so outputs land in our temp folder
        import yaml
        cfg = yaml.safe_load(open(CONFIG_PATH))
        cfg["paths"]["data_dir"] = str(tmp_dir / "data")
        tmp_cfg = tmp_dir / "config.yaml"
        with open(tmp_cfg, "w") as f:
            yaml.dump(cfg, f)

        # ── Phase 2: Rule matching ────────────────────────────
        emit(job_id, "RULES", "lt-phase", "Loading insight rules & matching triggers...")
        from prompter.prompt_builder import PromptBuilder
        pb = PromptBuilder(str(tmp_cfg))
        # count matched rules
        import yaml as _y
        from pathlib import Path as _P
        rules_dir = PROJECT_ROOT / "prompts" / "rules"
        all_rules = []
        for yf in rules_dir.glob("*.yaml"):
            d = _y.safe_load(open(yf))
            if d and "rules" in d:
                all_rules.extend(d["rules"])
        matched = [r for r in all_rules if any(t in c_code for t in r.get("trigger", []))]
        if matched:
            names = ", ".join(r["name"] for r in matched)
            emit(job_id, "RULES", "lt-phase",
                 f"Matched <b>{len(matched)}</b> rules: <span class='hl'>{names}</span>")
        else:
            emit(job_id, "RULES", "lt-phase",
                 "No specific rules matched — using standard Safe Rust practices")

        # ── Phase 3: Skeleton generation (Tree-sitter) ────────
        emit(job_id, "SKEL", "lt-phase", "Generating Rust skeleton via Tree-sitter...")
        try:
            from analyzer.skeleton_generator import SkeletonGenerator
            sg = SkeletonGenerator(str(tmp_cfg))
            skeleton = sg.generate_rust_skeleton(c_file, c_code)
            emit(job_id, "SKEL", "lt-ok",
                 f"Skeleton generated ({len(skeleton)} chars)")
        except Exception as e:
            skeleton = ""
            emit(job_id, "SKEL", "lt-fix",
                 f"Skeleton skipped: {str(e)[:80]}")

        # ── Phase 4: DFG / Semantic fingerprint ───────────────
        emit(job_id, "DFG", "lt-phase", "Running Clang DFG semantic analysis...")
        try:
            from analyzer.c_semantic_extractor import CSemanticExtractor
            extractor = CSemanticExtractor()
            fingerprint = extractor.extract_semantic_fingerprint(c_file, "main")
            fp_str = extractor.format_for_prompt(fingerprint)
            emit(job_id, "DFG", "lt-ok",
                 f"DFG fingerprint extracted ({len(fp_str)} chars)")
        except Exception as e:
            fp_str = ""
            emit(job_id, "DFG", "lt-fix",
                 f"DFG skipped (libclang): {str(e)[:80]}")

        # ── Phase 5: RAG retrieval ────────────────────────────
        emit(job_id, "RAG", "lt-phase", "Searching RAG vector DB for examples...")
        try:
            from prompter.rag_retriever import RagRetriever
            ex_dir = PROJECT_ROOT / "data" / "examples"
            ex_dir.mkdir(parents=True, exist_ok=True)
            rag = RagRetriever(db_path=str(tmp_dir / "vector_db"))
            rag.seed_database(ex_dir)
            snippets = rag.retrieve_examples(fingerprint if fp_str else {})
            rag_str  = rag.format_for_prompt(snippets)
            emit(job_id, "RAG", "lt-ok",
                 f"Retrieved <b>{len(snippets)}</b> relevant Safe Rust examples")
        except Exception as e:
            rag_str = ""
            emit(job_id, "RAG", "lt-fix",
                 f"RAG skipped: {str(e)[:80]}")

        # ── Phase 6: LLM Translation ──────────────────────────
        emit(job_id, "LLM", "lt-llm",
             "Assembling master prompt & sending to LLM...")
        master_msgs = pb.build_master_prompt(
            c_code=c_code,
            c2rust_code="// c2rust not available in web mode",
            c_fingerprint_str=fp_str,
            rag_examples_str=rag_str,
            skeleton_code=skeleton,
        )
        raw_response = _claude_instance.generate(master_msgs)

        import re
        # Parse plan + code from structured markdown
        plan_marker = "### 1. TRANSLATION PLAN"
        code_marker = "### 2. SAFE RUST CODE"
        plan_s = raw_response.find(plan_marker)
        code_s = raw_response.find(code_marker)
        if plan_s != -1:
            plan_text = raw_response[plan_s + len(plan_marker):
                                     code_s if code_s != -1 else len(raw_response)].strip()
            first_line = plan_text.splitlines()[0][:160] if plan_text else ""
            if first_line:
                emit(job_id, "PLAN", "lt-phase", f"💡 {first_line}")

        target = raw_response[code_s:] if code_s != -1 else raw_response
        m = re.search(r"```(?:rust)?\s*(.*?)\s*```", target, re.DOTALL)
        initial_code = m.group(1).strip() if m else raw_response.strip()

        emit(job_id, "LLM", "lt-ok",
             f"Initial translation complete ({len(initial_code)} chars)")

        # Save to file for repair agent
        (tmp_dir / "data" / "outputs").mkdir(parents=True, exist_ok=True)
        raw_rs = tmp_dir / "data" / "outputs" / "input.rs"
        raw_rs.write_text(initial_code, encoding="utf-8")

        # ── Phase 7: Repair Loop ──────────────────────────────
        emit(job_id, "REPAIR", "lt-phase",
             "Starting auto-repair loop (max <b>5</b> attempts)...")
        try:
            from agent.repair_agent import RepairAgent
            repair = RepairAgent(str(tmp_cfg))
            final_rs_path = repair.run(raw_rs, "input", is_bin=True)

            if final_rs_path and final_rs_path.exists():
                final_code = final_rs_path.read_text(encoding="utf-8")
                unsafe_n   = len(re.findall(r"\bunsafe\b", final_code))
                raw_ptr_n  = len(re.findall(r"\*mut|\*const", final_code))
                emit(job_id, "DONE", "lt-ok",
                     f'<span class="ok">✅ Pipeline SUCCESS</span> — '
                     f'unsafe blocks: <b>{unsafe_n}</b>, raw ptrs: <b>{raw_ptr_n}</b>')
                job["result"]  = final_code
                job["success"] = True
            else:
                # repair failed, return best effort
                emit(job_id, "DONE", "lt-fix",
                     "Repair loop exhausted — returning best-effort code")
                job["result"]  = initial_code
                job["success"] = False

        except Exception as e:
            emit(job_id, "REPAIR", "lt-fix",
                 f"Repair skipped: {str(e)[:120]}")
            job["result"]  = initial_code
            job["success"] = False

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        emit(job_id, "ERR", "lt-err",
             f'<span class="er">Fatal error: {str(e)}</span>')
        job["error"] = str(e)
        job["result"] = ""
    finally:
        job["done"] = True


# ── Routes ────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("web", "index.html")


@app.route("/api/convert", methods=["POST"])
def convert():
    data    = request.get_json(force=True)
    c_code  = data.get("c_code", "").strip()
    api_key = data.get("api_key", "").strip()

    if not c_code:
        return jsonify({"error": "No C code provided"}), 400
    if not api_key:
        return jsonify({"error": "No API key provided"}), 400

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"logs": [], "done": False, "result": "", "error": "", "success": False}

    t = threading.Thread(target=run_pipeline_job, args=(job_id, c_code, api_key), daemon=True)
    t.start()

    return jsonify({"job_id": job_id})


@app.route("/api/poll/<job_id>")
def poll(job_id):
    """
    Long-poll endpoint. Returns new log lines since `since` index,
    plus done/result when the job finishes.
    """
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Unknown job"}), 404

    since = int(request.args.get("since", 0))
    new_logs = job["logs"][since:]

    resp = {
        "logs":  new_logs,
        "total": len(job["logs"]),
        "done":  job["done"],
    }
    if job["done"]:
        resp["result"]  = job["result"]
        resp["error"]   = job["error"]
        resp["success"] = job["success"]
        # clean up after delivery
        # (keep for 5 min in case of re-poll, GC not implemented here)

    return jsonify(resp)


if __name__ == "__main__":
    web_dir = PROJECT_ROOT / "web"
    web_dir.mkdir(exist_ok=True)
    print("=" * 60)
    print("🔥  Oxidizer Web Server")
    print("    http://localhost:5000")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
