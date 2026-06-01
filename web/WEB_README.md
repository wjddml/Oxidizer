# Oxidizer Web Server — Setup & Run

## Requirements

- Python 3.10+
- Rust + Cargo installed (`rustup`)
- `c2rust` installed (optional — only for reference unsafe code)
- An Anthropic API key (get one at https://console.anthropic.com)

## Install Python dependencies

```bash
cd Oxidizer-main
pip install flask flask-cors anthropic
# Full deps (if not already installed):
pip install -r requirements.txt
```

## Set your API key

Either enter it in the browser UI (it saves to localStorage), or set it as an environment variable:

```bash
export ANTHROPIC_API_KEY="sk-ant-api03-..."
```

## Run the server

```bash
cd Oxidizer-main
python server.py
```

Then open **http://localhost:5000** in your browser.

## What happens when you click "Run Oxidizer"

1. **Rules** — All YAML insight rules from `prompts/rules/*.yaml` are matched against your C code
2. **Skeleton** — Tree-sitter generates a Rust structural skeleton for context
3. **DFG** — Clang analyzes pointer/variable usage patterns (requires libclang)
4. **RAG** — ChromaDB retrieves similar Safe Rust examples from `data/examples/`
5. **LLM** — Claude translates your C code using the assembled master prompt
6. **Repair** — `cargo check` validates the output; errors are fed back to Claude up to 5 times
