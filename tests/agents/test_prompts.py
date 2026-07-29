import pytest

from data_agent.agents.prompts.milvus_scanner import (
    MILVUS_AGENT_INSTRUCTION,
    MILVUS_AGENT_NAME,
)
from data_agent.agents.prompts.mongodb_scanner import (
    MONGODB_AGENT_INSTRUCTION,
    MONGODB_AGENT_NAME,
)
from data_agent.agents.prompts.root_orchestrator import (
    ROOT_AGENT_DESCRIPTION,
    ROOT_AGENT_INSTRUCTION,
    ROOT_AGENT_NAME,
)
from data_agent.agents.prompts.title_generator import (
    SYSTEM_AGENT_INSTRUCTION,
    SYSTEM_AGENT_NAME,
)

AGENT_NAMES = [
    MILVUS_AGENT_NAME,
    MONGODB_AGENT_NAME,
    ROOT_AGENT_NAME,
    SYSTEM_AGENT_NAME,
]

INSTRUCTIONS = [
    pytest.param(MILVUS_AGENT_INSTRUCTION, id="milvus"),
    pytest.param(MONGODB_AGENT_INSTRUCTION, id="mongodb"),
    pytest.param(ROOT_AGENT_INSTRUCTION, id="root"),
    pytest.param(SYSTEM_AGENT_INSTRUCTION, id="title"),
]

UNFINISHED = pytest.mark.xfail(
    strict=True,
    reason=(
        "MONGODB_AGENT_INSTRUCTION is still a draft: it contains a "
        "'[TODO: FILL IN ...]' marker for the SEHA plant type and rules 11-15 are "
        "placeholder notes. Remove this marker once the prompt is finished."
    ),
)

DRAFTABLE_INSTRUCTIONS = [
    pytest.param(MILVUS_AGENT_INSTRUCTION, id="milvus"),
    pytest.param(MONGODB_AGENT_INSTRUCTION, id="mongodb", marks=UNFINISHED),
    pytest.param(ROOT_AGENT_INSTRUCTION, id="root"),
    pytest.param(SYSTEM_AGENT_INSTRUCTION, id="title"),
]


class TestAgentNames:

    def test_expected_names(self):
        assert MILVUS_AGENT_NAME == "milvus_scanner"
        assert MONGODB_AGENT_NAME == "mongodb_scanner"
        assert ROOT_AGENT_NAME == "root_orchestrator"
        assert SYSTEM_AGENT_NAME == "system_agent"

    def test_names_are_unique(self):
        assert len(set(AGENT_NAMES)) == len(AGENT_NAMES)

    @pytest.mark.parametrize("name", AGENT_NAMES)
    def test_names_are_valid_identifiers(self, name):
        assert name.isidentifier()
        assert name == name.lower()


class TestInstructions:

    @pytest.mark.parametrize("instruction", INSTRUCTIONS)
    def test_instructions_are_not_empty(self, instruction):
        assert instruction.strip()

    @pytest.mark.parametrize("instruction", INSTRUCTIONS)
    def test_instructions_have_no_format_placeholders(self, instruction):
        assert "{}" not in instruction

    @pytest.mark.parametrize("instruction", DRAFTABLE_INSTRUCTIONS)
    def test_instructions_are_finished(self, instruction):
        assert "TODO" not in instruction
        assert "FILL IN" not in instruction

    def test_the_root_description_is_a_single_line(self):
        assert ROOT_AGENT_DESCRIPTION.strip()
        assert "\n" not in ROOT_AGENT_DESCRIPTION

    def test_the_root_instruction_names_both_scanners(self):
        assert MILVUS_AGENT_NAME in ROOT_AGENT_INSTRUCTION
        assert MONGODB_AGENT_NAME in ROOT_AGENT_INSTRUCTION

    def test_the_title_instruction_forbids_the_words_it_lists(self):
        for word in ("session", "agent", "system"):
            assert word in SYSTEM_AGENT_INSTRUCTION
