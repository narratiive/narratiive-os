import unittest
from runtime.agency_executive_brief import AgencyExecutiveBriefService, AgencyBriefPeriod
from runtime.agency_state import AgencyState, AgencyItem, AgencyArea
from runtime.founder_brief import material_founder_lines


class FounderBriefLimitTests(unittest.TestCase):
    def test_agency_brief_has_three_unique_material_items_in_both_periods(self):
        items = [AgencyItem(str(i), AgencyArea.DELIVERY, f'Delivery {i}', 'blocked', 'Review the draft.', blocked=True, requires_matt=True) for i in range(6)]
        items.append(AgencyItem('noise', AgencyArea.OPERATIONS, 'Routine check', 'active', 'Check again.'))
        state = AgencyState.from_items('synthetic', items)
        for period in AgencyBriefPeriod:
            text = AgencyExecutiveBriefService().build(state, period).render_compact()
            self.assertEqual(sum(line.startswith('- ') for line in text.splitlines()), 3)
            self.assertEqual(text.count('Delivery 0'), 1)
            self.assertNotIn('Routine check', text)

    def test_runtime_references_removed_and_decisions_deduplicated(self):
        lines = material_founder_lines(('workflow:private-run:Review Loom Loft',) * 2, ('workstream:workflow:private-other:Resolve missing evidence', 'Third risk', 'Fourth risk'))
        self.assertEqual(len(lines), 3)
        self.assertNotIn('private-', ' '.join(lines))
        self.assertEqual(lines[0], 'Review Loom Loft')
