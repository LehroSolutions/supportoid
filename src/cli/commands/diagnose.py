"""Diagnose — Full system diagnostic (from github-copilot-cli patterns)"""
import sys, importlib
from pathlib import Path

def run(base: Path, verbose: bool = False) -> dict:
    results = {}
    py = sys.version_info
    results['python'] = {"status": "ok" if py.minor >= 11 else "warn", "version": f"{py.major}.{py.minor}.{py.micro}"}
    for dep, name in [("sklearn","scikit-learn"),("numpy","numpy"),("pytest","pytest")]:
        try:
            importlib.import_module(dep)
            results[name] = {"status": "ok"}
        except ImportError:
            results[name] = {"status": "error", "fix": f"pip install {name}"}
    agents_dir = base / "src" / "agents"
    expected = [
        "classifier",
        "empathy",
        "knowledge",
        "respond",
        "escalation",
        "feedback",
        "model_router",
        "response_comparator",
        "security_layer",
        "quality",
        "cost_tracker",
        "voice_output",
        "personaplex_integration",
        "llm_gateway",
        "support_response",
    ]
    agents = {f: "ok" if (agents_dir / f"{f}.py").exists() else "missing" for f in expected}
    results['agents'] = agents
    results['security'] = {"status": "ok" if (agents_dir / "security_layer.py").exists() else "error"}
    results['tests'] = {"status": "ok", "suites": len(list((base/"tests").glob("test_*.py")))}
    return results

def format_results(results: dict) -> str:
    lines, sep = [], '='*50
    lines.append(sep)
    lines.append(f"  SupportOID Diagnostic Report")
    lines.append(sep)
    lines.append(f"  PASSING: {sum(1 for v in results.values() if isinstance(v, dict) and v.get('status') == 'ok')}")
    lines.append('-'*50)
    for k, v in results.items():
        if isinstance(v, dict) and "status" in v:
            s = "[OK]" if v["status"] == "ok" else "[ERR]" if v["status"] == "error" else "[WARN]"
            lines.append(f"  {s} {k}: {v.get('version', v.get('status', ''))}")
        elif isinstance(v, dict):
            lines.append(f"  -- {k} --")
            for agent, status in v.items():
                icon = "[OK]" if status == "ok" else "[MISSING]"
                lines.append(f"    {icon} {agent}")
    lines.append('-'*50)
    return '\n'.join(lines)

def execute(base: Path, verbose: bool = False) -> None:
    results = run(base, verbose)
    print(format_results(results))
