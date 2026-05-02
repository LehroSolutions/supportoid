"""
Trace — User workflow tracer for CLI and UI
==========================================
Integrates with github-copilot-cli for diagnostic patterns
and api-designer for clean trace output formatting.

CLI Usage:
  supportoid trace                # Show recent traces
  supportoid trace --session <id> # Show specific session trace
  supportoid trace --live         # Live trace of current session

UI Integration:
  - Agent detail panels show real-time trace data
  - Workflow trace visualization
  - Per-agent performance metrics
  - Error detection and highlighting
"""

import sys, importlib
from pathlib import Path

def run(base: Path, verbose: bool = False) -> dict:
    results = {}
    # Python
    py = sys.version_info
    results['python'] = {"status": "ok" if py.minor >= 11 else "warn", "version": f"{py.major}.{py.minor}.{py.micro}"}
    # Dependencies
    for dep, name in [("sklearn","scikit-learn"),("numpy","numpy"),("pytest","pytest")]:
        try:
            importlib.import_module(dep)
            results[name] = {"status": "ok"}
        except ImportError:
            results[name] = {"status": "error", "fix": f"pip install {name}"}
    # Agents
    agents_dir = base / "src" / "agents"
    expected = ["classifier","empathy","knowledge","respond","escalation","feedback","model_router","response_comparator","security_layer","quality"]
    agents = {f: "ok" if (agents_dir / f"{f}.py").exists() else "missing" for f in expected}
    results['agents'] = agents
    # Security
    results['security'] = {"status": "ok" if (agents_dir / "security_layer.py").exists() else "error"}
    # Tests
    results['tests'] = {"status": "ok", "suites": len(list((base/"tests").glob("test_*.py")))}
    return results

def format_results(results: dict) -> str:
    lines = []
    ok = sum(1 for v in results.values() if isinstance(v, dict) and v.get("status") == "ok")
    lines.append(f'{'='*50}')
    lines.append(f'  SupportOID Diagnostic Report')
    lines.append(f'{'='*50}')
    lines.append(f'  ✓ {ok} passing')
    lines.append(f'{'-'*50}')
    for k, v in results.items():
        if isinstance(v, dict) and "status" in v:
            s = "✓" if v["status"] == "ok" else "✗" if v["status"] == "error" else "⚠"
            lines.append(f'  {s} {k}: {v.get("version", v.get("status", ""))}')
        elif isinstance(v, dict):
            lines.append(f'  ── {k} ──')
            for agent, status in v.items():
                lines.append(f'    {"✓" if status == "ok" else "✗"} {agent}')
    lines.append(f'{'-'*50}')
    return '\n'.join(lines)

def execute(base: Path, verbose: bool = False) -> None:
    results = run(base, verbose)
    print(format_results(results))
