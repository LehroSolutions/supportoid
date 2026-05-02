"""
SupportOID Workflow Tracer — CLI + UI integration
====================================================
Traces user workflows through all 7 agents in real-time.
Integrated into UI (optional panel) and CLI (standalone tool).
"""
import json, time, os
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field

@dataclass
class AgentStep:
    agent: str
    action: str
    data: dict
    start_time: float
    end_time: float = 0.0
    status: str = "processing"  # processing, success, warning, error

@dataclass
class WorkflowTrace:
    session_id: str
    user_input: str
    start_time: float
    steps: List[AgentStep] = field(default_factory=list)
    final_response: str = ""
    end_time: float = 0.0

    @property
    def duration(self):
        return (self.end_time - self.start_time) if self.end_time else (time.time() - self.start_time)

    def to_dict(self):
        return {
            "session_id": self.session_id,
            "user_input": self.user_input,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": round(self.duration, 3),
            "steps": [
                {
                    "agent": s.agent,
                    "action": s.action,
                    "status": s.status,
                    "duration_ms": round((s.end_time - s.start_time) * 1000, 2) if s.end_time else None,
                    "data": s.data
                }
                for s in self.steps
            ],
            "final_response": self.final_response,
            "duration_s": round(self.duration, 3)
        }

class WorkflowTracer:
    def __init__(self, base_path: str = None):
        self.base = base_path or str(Path(__file__).parent.parent.parent)
        self.traces_dir = Path(self.base) / "src" / "traces"
        self.traces_dir.mkdir(parents=True, exist_ok=True)
        self.active: Dict[str, WorkflowTrace] = {}
        self.completed: List[WorkflowTrace] = []

    def start(self, session_id: str, user_input: str) -> WorkflowTrace:
        trace = WorkflowTrace(session_id=session_id, user_input=user_input, start_time=time.time())
        self.active[session_id] = trace
        return trace

    def step(self, session_id: str, agent: str, action: str, data: dict, status: str = "success") -> Optional[AgentStep]:
        trace = self.active.get(session_id)
        if not trace: return None
        step = AgentStep(agent=agent, action=action, data=data, start_time=time.time(), end_time=time.time(), status=status)
        trace.steps.append(step)
        return step

    def begin_step(self, session_id: str, agent: str, action: str, data: dict = None) -> Optional[AgentStep]:
        trace = self.active.get(session_id)
        if not trace: return None
        step = AgentStep(agent=agent, action=action, data=data or {}, start_time=time.time())
        trace.steps.append(step)
        return step

    def end_step(self, session_id: str, status: str = "success") -> Optional[AgentStep]:
        trace = self.active.get(session_id)
        if not trace or not trace.steps: return None
        step = trace.steps[-1]
        step.end_time = time.time()
        step.status = status
        return step

    def complete(self, session_id: str, response: str, error: str = None) -> WorkflowTrace:
        trace = self.active.pop(session_id, None)
        if not trace: return None
        trace.end_time = time.time()
        trace.final_response = response
        if error: trace.error = error
        self.completed.append(trace)
        # Save to disk
        trace_file = self.traces_dir / f"{session_id}.json"
        with open(trace_file, 'w') as f:
            json.dump(trace.to_dict(), f, indent=2)
        return trace

    def get_trace(self, session_id: str) -> Optional[dict]:
        trace_file = self.traces_dir / f"{session_id}.json"
        if trace_file.exists():
            with open(trace_file) as f:
                return json.load(f)
        return None

    def list_traces(self, limit: int = 20) -> List[dict]:
        if not self.traces_dir.exists():
            return []
        sessions = []
        for f in sorted(self.traces_dir.glob("*.json"), reverse=True)[:limit]:
            with open(f) as fh:
                data = json.load(fh)
            sessions.append({
                "session_id": data.get("session_id"),
                "duration_s": round(data.get("duration_s", 0), 2),
                "steps": len(data.get("steps", [])),
                "error": data.get("error"),
                "user_input": (data.get("user_input") or "")[:50]
            })
        return sessions

    def cli_output(self, trace_data: dict) -> str:
        lines = [f"{'='*60}"]
        lines.append(f"  Trace: {trace_data.get('session_id')}")
        lines.append(f"{'='*60}")
        lines.append(f"  Input: {trace_data.get('user_input', '')}")
        lines.append(f"  Duration: {trace_data.get('duration_s', 0)}s")
        lines.append(f"  Error: {trace_data.get('error') or 'None'}")
        lines.append(f"{'-'*60}")
        for i, s in enumerate(trace_data.get('steps', [])):
            icon = {'success':'✓','warning':'⚠','error':'✗'}.get(s.get('status'),'…')
            lines.append(f"  {i+1}. {icon} [{s.get('agent')}] {s.get('action')}")
        lines.append(f"{'='*60}")
        return "\n".join(lines)

# Global tracer instance
tracer = WorkflowTracer()
