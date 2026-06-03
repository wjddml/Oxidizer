"""
Oxidizer Web Server — run from inside Oxidizer-main/:
    pip install flask flask-cors anthropic
    python server.py
Then open http://localhost:5000
"""

import os, sys, re, json, tempfile, shutil, threading, uuid, yaml
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# ── Make src/ importable ──────────────────────────────────────
ROOT = Path(__file__).resolve().parent          # …/Oxidizer-main/
SRC  = ROOT / "src"
if not SRC.exists():
    sys.exit(f"ERROR: 'src/' folder not found next to server.py\n"
             f"  Expected: {SRC}\n"
             f"  Make sure server.py is inside Oxidizer-main/")
sys.path.insert(0, str(SRC))

app = Flask(__name__, static_folder=str(ROOT / "web"))
CORS(app)

CONFIG = str(ROOT / "config.yaml")

# ── Job store ─────────────────────────────────────────────────
jobs: dict = {}   # job_id -> {logs, done, result, error, success}

def emit(jid, tag, cls, msg):
    jobs[jid]["logs"].append({"tag": tag, "cls": cls, "msg": msg})

# ── Pipeline thread ───────────────────────────────────────────
def run_pipeline(jid: str, c_code: str, api_key: str):
    job = jobs[jid]
    os.environ["ANTHROPIC_API_KEY"] = api_key   # set before any import

    try:
        emit(jid, "INIT", "lt-init", "Oxidizer pipeline started")

        # ── Temp workspace ────────────────────────────────────
        tmp = Path(tempfile.mkdtemp(prefix="oxidizer_"))
        c_file = tmp / "input.c"
        c_file.write_text(c_code, encoding="utf-8")

        # Patch config paths to use tmp dir for outputs
        cfg = yaml.safe_load(open(CONFIG))
        cfg["paths"]["data_dir"] = str(tmp / "data")
        tmp_cfg = tmp / "config.yaml"
        tmp_cfg.write_text(yaml.dump(cfg))
        (tmp / "data" / "outputs").mkdir(parents=True, exist_ok=True)

        emit(jid, "SETUP", "lt-phase",
             f"Workspace: <b>{tmp.name}</b>")

        # ── Prompter (no LLM dependency) ──────────────────────
        emit(jid, "RULES", "lt-phase", "Loading insight rules & matching triggers…")
        from prompter.prompt_builder import PromptBuilder
        pb = PromptBuilder(str(tmp_cfg))

        rules_dir = ROOT / "prompts" / "rules"
        all_rules = []
        for yf in rules_dir.glob("*.yaml"):
            d = yaml.safe_load(open(yf))
            if d and "rules" in d:
                all_rules.extend(d["rules"])
        matched = [r for r in all_rules
                   if any(t in c_code for t in r.get("trigger", []))]
        if matched:
            names = ", ".join(r["name"] for r in matched)
            emit(jid, "RULES", "lt-phase",
                 f"Matched <b>{len(matched)}</b> rules: <span class='hl'>{names}</span>")
        else:
            emit(jid, "RULES", "lt-phase",
                 "No specific rules matched — using standard practices")

        # ── Skeleton (Tree-sitter) ────────────────────────────
        emit(jid, "SKEL", "lt-phase", "Generating Rust skeleton via Tree-sitter…")
        skeleton = ""
        try:
            from analyzer.skeleton_generator import SkeletonGenerator
            sg = SkeletonGenerator(str(tmp_cfg))
            skeleton = sg.generate_rust_skeleton(c_file, c_code)
            emit(jid, "SKEL", "lt-ok",
                 f"Skeleton generated ({len(skeleton)} chars)")
        except Exception as e:
            emit(jid, "SKEL", "lt-fix", f"Skeleton skipped: {str(e)[:100]}")

        # ── DFG / Semantic fingerprint ────────────────────────
        emit(jid, "DFG", "lt-phase", "Running semantic analysis…")
        fp_str, fingerprint = "", {}
        try:
            from analyzer.c_semantic_extractor import CSemanticExtractor
            ex = CSemanticExtractor()
            fingerprint = ex.extract_semantic_fingerprint(c_file, "main")
            fp_str = ex.format_for_prompt(fingerprint)
            emit(jid, "DFG", "lt-ok",
                 f"DFG fingerprint extracted ({len(fp_str)} chars)")
        except Exception as e:
            emit(jid, "DFG", "lt-fix", f"DFG skipped: {str(e)[:100]}")

        # ── RAG retrieval ─────────────────────────────────────
        emit(jid, "RAG", "lt-phase", "Searching RAG vector DB for examples…")
        rag_str = ""
        try:
            from prompter.rag_retriever import RagRetriever
            ex_dir = ROOT / "data" / "examples"
            rag = RagRetriever(db_path=str(tmp / "vector_db"))
            rag.seed_database(ex_dir)
            snippets = rag.retrieve_examples(fingerprint)
            rag_str  = rag.format_for_prompt(snippets)
            emit(jid, "RAG", "lt-ok",
                 f"Retrieved <b>{len(snippets)}</b> relevant examples")
        except Exception as e:
            emit(jid, "RAG", "lt-fix", f"RAG skipped: {str(e)[:100]}")

        # ── LLM translation ───────────────────────────────────
        emit(jid, "LLM", "lt-llm",
             "Assembling master prompt → calling <b>Claude</b>…")
        master_msgs = pb.build_master_prompt(
            c_code=c_code,
            c2rust_code="// c2rust not available in web mode",
            c_fingerprint_str=fp_str,
            rag_examples_str=rag_str,
            skeleton_code=skeleton,
        )

        # Use the factory — now properly supports claude via config.yaml
        from llm.llm_factory import create_llm_client
        llm = create_llm_client(str(tmp_cfg))
        raw = llm.generate(master_msgs)

        # Parse plan + code from structured markdown
        plan_m = "### 1. TRANSLATION PLAN"
        code_m = "### 2. SAFE RUST CODE"
        ps, cs = raw.find(plan_m), raw.find(code_m)
        if ps != -1:
            plan_text = raw[ps + len(plan_m): cs if cs != -1 else len(raw)].strip()
            first = plan_text.splitlines()[0][:180] if plan_text else ""
            if first:
                emit(jid, "PLAN", "lt-phase", f"💡 {first}")

        target = raw[cs:] if cs != -1 else raw
        m = re.search(r"```(?:rust)?\s*(.*?)\s*```", target, re.DOTALL)
        initial_code = m.group(1).strip() if m else raw.strip()
        emit(jid, "LLM", "lt-ok",
             f"Translation done ({len(initial_code)} chars)")

        # Save for repair agent
        raw_rs = tmp / "data" / "outputs" / "input.rs"
        raw_rs.write_text(initial_code, encoding="utf-8")

        # ── Repair loop ───────────────────────────────────────
        emit(jid, "REPAIR", "lt-phase",
             "Starting auto-repair loop (max <b>5</b> attempts)…")
        final_code = initial_code
        success    = False
        try:
            from agent.repair_agent import RepairAgent
            ra = RepairAgent(str(tmp_cfg))
            result = ra.run(raw_rs, "input", is_bin=True)
            if result and result.exists():
                final_code = result.read_text(encoding="utf-8")
                success    = True
                u = len(re.findall(r"\bunsafe\b", final_code))
                p = len(re.findall(r"\*mut|\*const", final_code))
                emit(jid, "DONE", "lt-ok",
                     f'<span class="ok">✅ SUCCESS</span> — '
                     f'unsafe: <b>{u}</b>, raw ptrs: <b>{p}</b>')
            else:
                emit(jid, "DONE", "lt-fix",
                     "Repair exhausted — returning best-effort code")
        except Exception as e:
            emit(jid, "REPAIR", "lt-fix", f"Repair skipped: {str(e)[:120]}")

        job["result"]  = final_code
        job["success"] = success

    except Exception as e:
        import traceback
        emit(jid, "ERR", "lt-err",
             f'<span class="er">Fatal: {str(e)}</span>')
        job["error"] = str(e)
    finally:
        job["done"] = True


# ── Routes ────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory(str(ROOT / "web"), "index.html")

@app.route("/api/convert", methods=["POST"])
def convert():
    data    = request.get_json(force=True)
    c_code  = data.get("c_code", "").strip()
    api_key = data.get("api_key", "").strip()
    if not c_code:  return jsonify({"error": "No C code provided"}), 400
    if not api_key: return jsonify({"error": "No API key provided"}), 400

    jid = str(uuid.uuid4())
    jobs[jid] = {"logs": [], "done": False, "result": "", "error": "", "success": False}
    threading.Thread(target=run_pipeline, args=(jid, c_code, api_key), daemon=True).start()
    return jsonify({"job_id": jid})

@app.route("/api/poll/<jid>")
def poll(jid):
    job = jobs.get(jid)
    if not job: return jsonify({"error": "Unknown job"}), 404
    since    = int(request.args.get("since", 0))
    new_logs = job["logs"][since:]
    resp = {"logs": new_logs, "total": len(job["logs"]), "done": job["done"]}
    if job["done"]:
        resp["result"]  = job["result"]
        resp["error"]   = job["error"]
        resp["success"] = job["success"]
    return jsonify(resp)

if __name__ == "__main__":
    print("=" * 60)
    print("🔥  Oxidizer Web Server")
    print(f"    Root : {ROOT}")
    print(f"    src/ : {SRC}")
    print("    URL  : http://localhost:5000")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
