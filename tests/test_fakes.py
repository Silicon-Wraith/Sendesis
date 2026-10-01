import pytest
from agno.agent import Agent
from agno.run.base import RunStatus

from fakes import ScriptedModel


def test_scripted_reply_reaches_the_agent():
    model = ScriptedModel(replies=['{"ok": true}'])
    out = Agent(model=model, telemetry=False).run("hi")
    assert out.status != RunStatus.error
    assert out.content == '{"ok": true}'
    assert out.model_provider_data["agno_cli_models"]["observed_model"] == "scripted-1"
    assert model.config_fingerprint() == "f" * 64


def test_scripted_exception_becomes_an_error_run():
    out = Agent(model=ScriptedModel(replies=[RuntimeError("boom")]), telemetry=False).run("hi")
    assert out.status == RunStatus.error
