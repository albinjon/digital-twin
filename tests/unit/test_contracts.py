import unittest

from pydantic import TypeAdapter

from digital_twin.config import load_teams
from digital_twin.domain.contracts import (
    Decision,
    MoveState,
    RequestHuman,
    StartImplementation,
)

decision_adapter = TypeAdapter(Decision)


class DecisionContractTests(unittest.TestCase):
    def test_discriminates_known_variants(self) -> None:
        decision = decision_adapter.validate_python(
            {"kind": "move_state", "target_lane": "Todo"}
        )
        self.assertIsInstance(decision, MoveState)

    def test_rejects_unknown_kind(self) -> None:
        with self.assertRaises(Exception):
            decision_adapter.validate_python({"kind": "delete_repo"})

    def test_no_generic_post_comment_variant(self) -> None:
        # Guards the "typed comments only" decision: nothing accepts free text
        # into an unstructured comment field.
        with self.assertRaises(Exception):
            decision_adapter.validate_python(
                {"kind": "post_comment", "body": "anything"}
            )

    def test_request_human_reason_is_constrained(self) -> None:
        with self.assertRaises(Exception):
            decision_adapter.validate_python(
                {"kind": "request_human", "reason": "vibes", "summary": "x"}
            )
        decision = decision_adapter.validate_python(
            {"kind": "request_human", "reason": "runtime_missing", "summary": "x"}
        )
        self.assertIsInstance(decision, RequestHuman)

    def test_start_implementation_round_trips(self) -> None:
        decision = decision_adapter.validate_python(
            {
                "kind": "start_implementation",
                "branch_name": "feature/ZBS-1-example",
                "task_spec": "do the thing",
            }
        )
        self.assertIsInstance(decision, StartImplementation)


class TeamsConfigTests(unittest.TestCase):
    def test_loads_configured_teams_and_authorizes_known_prefix(self) -> None:
        teams = load_teams()
        zbs = teams.team_for_prefix("ZBS")
        self.assertIsNotNone(zbs)
        self.assertEqual(zbs.github_repository, "Zenbuddhistiska-Samfundet/web")

    def test_unknown_prefix_is_unauthorized(self) -> None:
        teams = load_teams()
        self.assertIsNone(teams.team_for_prefix("NOPE"))


if __name__ == "__main__":
    unittest.main()
