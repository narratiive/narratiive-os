from __future__ import annotations

import unittest

from scripts.patch_n8n_inbound_upsert import (
    BRANCH,
    CREATE,
    EXISTING,
    MERGE,
    NORMALISE,
    PREPARE,
    QUERY,
    SYNC,
    patch_workflow,
)


class PatchN8nInboundUpsertTests(unittest.TestCase):
    def _nodes(self) -> list[dict]:
        return [
            {
                "name": NORMALISE,
                "parameters": {
                    "jsCode": "const body = $json.body || $json;\nconst tallyData = null;\nconst isTally =\n  Boolean(tallyData) ||\n  String(body.source || '').toLowerCase() === 'tally';\nconst lead = {\n  lead_id:\n    body.lead_id ||\n    body.leadId ||\n    body.id ||\n    (tallyData && (tallyData.responseId || tallyData.submissionId)) ||\n    '',\n};"
                },
            },
            {
                "name": CREATE,
                "parameters": {
                    "jsonBody": "={{ ({\n  properties: {\n    Contact: { title: [{ text: { content: $json.name } }] }\n  }\n}) }}",
                    "headerParameters": {
                        "parameters": [
                            {"name": "Authorization", "value": "Bearer secret"},
                            {"name": "Notion-Version", "value": "2022-06-28"},
                        ]
                    },
                },
            },
            {"name": SYNC, "parameters": {}},
            {
                "name": PREPARE,
                "parameters": {"jsCode": "const notionResult = $('Create Notion Lead1').first().json;"},
            },
        ]

    def test_patch_adds_upsert_path_and_removes_embedded_notion_secret(self) -> None:
        nodes, connections = patch_workflow(
            self._nodes(),
            {NORMALISE: {"main": [[{"node": CREATE, "type": "main", "index": 0}]]}},
            notion_credential_id="credential-1",
        )
        by_name = {node["name"]: node for node in nodes}
        self.assertTrue({QUERY, BRANCH, EXISTING, MERGE}.issubset(by_name))
        self.assertIn("sourceSubmissionId", by_name[NORMALISE]["parameters"]["jsCode"])
        self.assertIn("sourceType", by_name[NORMALISE]["parameters"]["jsCode"])
        self.assertIn("Source Submission ID", by_name[CREATE]["parameters"]["jsonBody"])
        self.assertIn("Inbound Message ID", by_name[CREATE]["parameters"]["jsonBody"])
        headers = by_name[CREATE]["parameters"]["headerParameters"]["parameters"]
        self.assertNotIn("authorization", {item["name"].casefold() for item in headers})
        self.assertEqual(by_name[CREATE]["credentials"]["notionApi"]["id"], "credential-1")
        self.assertIn(MERGE, by_name[PREPARE]["parameters"]["jsCode"])
        self.assertEqual(connections[NORMALISE]["main"][0][0]["node"], QUERY)
        self.assertEqual(connections[MERGE]["main"][0][0]["node"], SYNC)

    def test_patch_is_repeatable(self) -> None:
        first_nodes, first_connections = patch_workflow(
            self._nodes(), {}, notion_credential_id="credential-1"
        )
        second_nodes, second_connections = patch_workflow(
            first_nodes, first_connections, notion_credential_id="credential-1"
        )
        self.assertEqual(first_nodes, second_nodes)
        self.assertEqual(first_connections, second_connections)


if __name__ == "__main__":
    unittest.main()
