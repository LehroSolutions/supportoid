"""Tests for CLI and workflow tracer — round 6"""
import pytest, time, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

@pytest.fixture()
def tmp_tracer(tmp_path):
    from src.cli.trace import WorkflowTracer
    return WorkflowTracer(base_path=str(tmp_path))

@pytest.fixture()
def base():
    return Path(__file__).parent.parent

@pytest.fixture()
def settings(tmp_path):
    from src.config.settings import Settings
    return Settings(model_dir=str(tmp_path/"models"), kb_dir=str(tmp_path/"knowledge"),
                   feedback_dir=str(tmp_path/"feedback"), training_dir=str(tmp_path/"training"),
                   deployment_profile="test", seed_demo_kb_on_empty=True)

class TestCLI:
    def test_diagnose_passes(self, base):
        from src.cli.commands.diagnose import run
        results = run(base)
        assert 'agents' in results
        assert all(v == 'ok' for v in results.get('agents', {}).values())
        assert 'security' in results
        assert results['security']['status'] == 'ok'

    def test_diagnose_format(self, base):
        from src.cli.commands.diagnose import run, format_results
        results = run(base)
        output = format_results(results)
        assert 'Diagnostic Report' in output
        assert 'agents' in output

class TestWorkflowTracer:
    def test_start_session(self, tmp_tracer):
        t = tmp_tracer.start('test1', 'How do I reset my password?')
        assert t.session_id == 'test1'
        assert t.user_input == 'How do I reset my password?'

    def test_trace_step(self, tmp_tracer):
        tmp_tracer.start('test2', 'help')
        step = tmp_tracer.step('test2', 'classifier', 'classified', {'intent': 'general_question'})
        assert step is not None
        assert step.agent == 'classifier'

    def test_complete_session(self, tmp_tracer):
        tmp_tracer.start('test3', 'Refund please')
        tmp_tracer.step('test3', 'classifier', 'classified', {'intent': 'refund_request'})
        comp = tmp_tracer.complete('test3', 'Go to billing settings.')
        assert comp is not None
        assert comp.final_response == 'Go to billing settings.'

    def test_trace_saved_to_disk(self, tmp_tracer):
        tmp_tracer.start('test4', 'Billing?')
        tmp_tracer.step('test4', 'classifier', 'classified', {})
        tmp_tracer.complete('test4', 'Check billing settings.')
        trace_file = tmp_tracer.traces_dir / 'test4.json'
        assert trace_file.exists()

    def test_list_traces(self, tmp_tracer):
        tmp_tracer.start('list1', 'msg'); tmp_tracer.step('list1','c','',{})  ; tmp_tracer.complete('list1', 'resp')
        tmp_tracer.start('list2', 'msg2'); tmp_tracer.step('list2','c','',{}) ; tmp_tracer.complete('list2', 'resp2')
        traces = tmp_tracer.list_traces()
        assert len(traces) >= 2

    def test_get_single_trace(self, tmp_tracer):
        tmp_tracer.start('single1', 'test')
        tmp_tracer.step('single1', 'classifier', 'classified', {'intent': 'cq'})
        tmp_tracer.complete('single1', 'response')
        t = tmp_tracer.get_trace('single1')
        assert t is not None

    def test_trace_missing_session(self, tmp_tracer):
        t = tmp_tracer.get_trace('nonexistent')
        assert t is None

    def test_trace_format_cli(self, tmp_tracer):
        tmp_tracer.start('cli1', 'How much is pro?')
        tmp_tracer.step('cli1', 'classifier', 'classified', {'intent': 'billing_inquiry'})
        tmp_tracer.complete('cli1', 'Pro plan is $29/mo.')
        trace = tmp_tracer.get_trace('cli1')
        output = tmp_tracer.cli_output(trace)
        assert 'cli1' in output
        assert 'classified' in output

class TestTracerOrchestratorIntegration:
    def test_full_trace_through_orchestrator(self, settings):
        from src.orchestrator import Orchestrator
        from src.cli.trace import WorkflowTracer
        orch = Orchestrator(settings)
        orch.initialize()
        tracer = WorkflowTracer(base_path=str(Path(__file__).parent.parent))
        t = tracer.start('orch_test', 'How do I reset my password?')
        result = orch.process('How do I reset my password?', 'orch_test')
        tracer.step('orch_test', 'classifier', 'classified', {'intent': result['intent']})
        tracer.step('orch_test', 'empathy', 'analyzed', {'tone': result.get('tone', 'warm')})
        tracer.step('orch_test', 'knowledge', 'retrieved', {'results': 1})
        tracer.step('orch_test', 'response', 'generated', {'source': result.get('source', 'template')})
        tracer.step('orch_test', 'quality', 'scored', {'score': result['quality_score']})
        if result.get('should_escalate'):
            tracer.step('orch_test', 'escalation', 'triggered', {'role': result['escalation_role']})
        tracer.step('orch_test', 'feedback', 'recorded', {})
        comp = tracer.complete('orch_test', result['response'])
        assert comp is not None
        assert len(comp.steps) >= 6
        assert comp.final_response == result['response']

    def test_concurrent_traces(self, settings, base):
        from src.cli.trace import WorkflowTracer
        tracer = WorkflowTracer(base_path=str(base))
        for i in range(10):
            tracer.start(f'conc_{i}', f'message {i}')
            tracer.step(f'conc_{i}', 'classifier', 'classified', {'intent': f'intent_{i}'})
            tracer.complete(f'conc_{i}', f'response {i}')
        traces = tracer.list_traces()
        assert len(traces) >= 10
