"""Tests for services/entity_agents.py — entity-level specialized agents.

TDD: Verify agent configuration, action selection, orchestration, and error handling.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, call


# ── Agent Configuration ──


class TestEntityAgentConfig:
    """Verify each agent has the correct entity type and source focus."""

    def test_price_agent_has_correct_focus(self):
        from services.entity_agents import EntityAgentOrchestrator
        configs = {c.name: c for c in EntityAgentOrchestrator.AGENT_CONFIGS}
        price = configs["price_agent"]
        assert price.entity_type == "pricing"
        assert "cms_nadac" in price.sources
        assert price.enabled is True

    def test_trial_agent_has_correct_focus(self):
        from services.entity_agents import EntityAgentOrchestrator
        configs = {c.name: c for c in EntityAgentOrchestrator.AGENT_CONFIGS}
        trial = configs["trial_agent"]
        assert trial.entity_type == "trial"
        assert "clinical_trials_gov" in trial.sources

    def test_drug_agent_has_correct_focus(self):
        from services.entity_agents import EntityAgentOrchestrator
        configs = {c.name: c for c in EntityAgentOrchestrator.AGENT_CONFIGS}
        drug = configs["drug_agent"]
        assert drug.entity_type == "drug"
        assert "fda_orange_book" in drug.sources
        assert "openfda_labels" in drug.sources

    def test_company_agent_has_correct_focus(self):
        from services.entity_agents import EntityAgentOrchestrator
        configs = {c.name: c for c in EntityAgentOrchestrator.AGENT_CONFIGS}
        company = configs["company_agent"]
        assert company.entity_type == "company"
        assert "sec_edgar" in company.sources


# ── Agent Actions ──


class TestEntityAgentActions:
    """Verify each agent selects the correct scripts for its entity type."""

    def test_price_agent_selects_pricing_script(self):
        from services.entity_agents import EntityAgentOrchestrator
        configs = {c.name: c for c in EntityAgentOrchestrator.AGENT_CONFIGS}
        price = configs["price_agent"]
        script_modules = [s[0] for s in price.scripts]
        assert "scripts.fetch_nadac_pricing" in script_modules

    def test_trial_agent_uses_scheduler(self):
        """Trial agent uses scheduler.run_one instead of scripts."""
        from services.entity_agents import EntityAgentOrchestrator
        configs = {c.name: c for c in EntityAgentOrchestrator.AGENT_CONFIGS}
        trial = configs["trial_agent"]
        # Trial agent has no scripts — it uses scheduler.run_one()
        assert trial.scripts == []
        assert trial.use_scheduler is True

    def test_drug_agent_selects_enrich_drugs(self):
        from services.entity_agents import EntityAgentOrchestrator
        configs = {c.name: c for c in EntityAgentOrchestrator.AGENT_CONFIGS}
        drug = configs["drug_agent"]
        script_modules = [s[0] for s in drug.scripts]
        assert "scripts.enrich_drugs" in script_modules
        assert "scripts.clean_drug_names" in script_modules

    def test_company_agent_selects_enrich_companies(self):
        from services.entity_agents import EntityAgentOrchestrator
        configs = {c.name: c for c in EntityAgentOrchestrator.AGENT_CONFIGS}
        company = configs["company_agent"]
        script_modules = [s[0] for s in company.scripts]
        assert "scripts.dedup_companies" in script_modules
        assert "scripts.enrich_companies" in script_modules


# ── Orchestrator ──


class TestEntityAgentOrchestrator:
    """Verify orchestrator creates, runs, and manages agents."""

    def test_creates_all_agents(self):
        from services.entity_agents import EntityAgentOrchestrator
        db = MagicMock()
        orch = EntityAgentOrchestrator(db)
        assert len(orch.agents) == 4
        names = [a.config.name for a in orch.agents]
        assert "price_agent" in names
        assert "trial_agent" in names
        assert "drug_agent" in names
        assert "company_agent" in names

    @patch("services.entity_agents.EntityAgent.run")
    def test_run_all_agents(self, mock_run):
        from services.entity_agents import EntityAgentOrchestrator
        mock_run.return_value = {"status": "completed", "scripts_run": 1}

        db = MagicMock()
        orch = EntityAgentOrchestrator(db)
        result = orch.run_all(dry_run=True)

        assert mock_run.call_count == 4
        assert "agents" in result
        assert len(result["agents"]) == 4

    @patch("services.entity_agents.EntityAgent.run")
    def test_run_single_agent(self, mock_run):
        from services.entity_agents import EntityAgentOrchestrator
        mock_run.return_value = {"status": "completed", "scripts_run": 2}

        db = MagicMock()
        orch = EntityAgentOrchestrator(db)
        result = orch.run_one("drug_agent", dry_run=True)

        assert mock_run.call_count == 1
        assert result["status"] == "completed"

    @patch("services.entity_agents.EntityAgent.run")
    def test_dry_run_no_writes(self, mock_run):
        from services.entity_agents import EntityAgentOrchestrator
        mock_run.return_value = {"status": "completed", "scripts_run": 0, "dry_run": True}

        db = MagicMock()
        orch = EntityAgentOrchestrator(db)
        result = orch.run_all(dry_run=True)

        # Every call should have dry_run=True
        for c in mock_run.call_args_list:
            assert c == call(dry_run=True)

    @patch("services.entity_agents.EntityAgent.run")
    def test_returns_combined_summary(self, mock_run):
        from services.entity_agents import EntityAgentOrchestrator
        mock_run.return_value = {"status": "completed", "scripts_run": 1}

        db = MagicMock()
        orch = EntityAgentOrchestrator(db)
        result = orch.run_all()

        assert "total_elapsed_s" in result
        assert "agents" in result
        assert result["completed"] == 4
        assert result["failed"] == 0

    @patch("services.entity_agents.EntityAgent.run")
    def test_skips_agent_on_error(self, mock_run):
        from services.entity_agents import EntityAgentOrchestrator

        # First agent raises, rest succeed
        mock_run.side_effect = [
            RuntimeError("pricing API down"),
            {"status": "completed", "scripts_run": 0},
            {"status": "completed", "scripts_run": 2},
            {"status": "completed", "scripts_run": 1},
        ]

        db = MagicMock()
        orch = EntityAgentOrchestrator(db)
        result = orch.run_all()

        assert result["completed"] == 3
        assert result["failed"] == 1
        # All 4 agents were attempted
        assert len(result["agents"]) == 4

    @patch("services.entity_agents.EntityAgent._record_action")
    @patch("services.entity_agents.EntityAgent._execute_script")
    def test_wires_into_steward_actions(self, mock_exec, mock_record):
        from services.entity_agents import EntityAgent, EntityAgentConfig

        mock_exec.return_value = {"updated": 5}

        config = EntityAgentConfig(
            name="test_agent",
            entity_type="drug",
            description="test",
            sources=["test_src"],
            scripts=[("scripts.enrich_drugs", "run")],
            schedule_hours=24,
        )
        db = MagicMock()
        agent = EntityAgent(config, db)
        agent.run(dry_run=False)

        # Should have recorded at least one action
        assert mock_record.call_count >= 1
        # Verify action was recorded with agent name
        recorded_call = mock_record.call_args_list[0]
        assert "test_agent" in str(recorded_call) or recorded_call[0][0] == "scripts.enrich_drugs"

    def test_run_one_unknown_agent_raises(self):
        from services.entity_agents import EntityAgentOrchestrator
        db = MagicMock()
        orch = EntityAgentOrchestrator(db)

        with pytest.raises(ValueError, match="not_real_agent"):
            orch.run_one("not_real_agent")

    def test_list_agents_returns_dicts(self):
        from services.entity_agents import EntityAgentOrchestrator
        db = MagicMock()
        orch = EntityAgentOrchestrator(db)
        agents = orch.list_agents()

        assert len(agents) == 4
        for a in agents:
            assert "name" in a
            assert "entity_type" in a
            assert "sources" in a
            assert "description" in a
            assert "enabled" in a
