# Media Control Layer Test Report

Synthetic client: `Northstar Test Co`
Scope: existing Campaign Engine approved artefacts → read-only provider ingestion → normalisation → analysis → Tony report → audit/restart recovery.

Overall: **PASS** (8/8 stages passed)

| Stage | Result | Provider | Operation | State | Audit evidence | Elapsed ms |
|---|---|---|---|---|---|---:|
| existing_campaign_foundation | **PASS** | narratiive | `verify_campaign_engine_state` | asset_suite_approved | `campaign-engine validated` | 0.624 |
| meta_read_ingestion | **PASS** | meta | `get_performance` | performance_ingested | `media-3c82c08dd42b4c61b2848e0c` | 1.025 |
| tiktok_read_ingestion | **PASS** | tiktok | `get_performance` | performance_ingested | `media-72168d10b083f67a26346aae` | 0.882 |
| google_read_ingestion | **PASS** | google | `get_performance` | performance_ingested | `media-982f6a6f71619800e52a76b3` | 1.043 |
| restart_recovery | **PASS** | all | `replay_execution_journal` | recovered | `921a35164e50d717a355bd2e055f205a190eef3d425896940aea21409ac9474b` | 0.695 |
| analysis_and_recommendation | **PASS** | all | `analyse` | recommendations_pending_human_review | `derived_from_audited_snapshots` | 0.394 |
| tony_report | **PASS** | all | `/media northstar-test-co 7d` | attention_required | `read_only_query` | 0.521 |
| phase_one_write_prohibition | **PASS** | meta | `activate_campaign` | blocked | `media-9688165acaaac5ecac464a76` | 0.643 |

## Stage evidence

### existing_campaign_foundation — PASS

- Input: `{"client": "Northstar Test Co"}`
- Provider / operation: `narratiive / verify_campaign_engine_state`
- Validation: passed
- Resulting state: `asset_suite_approved`
- Audit event: `campaign-engine validated`
- Error: None
- Elapsed: 0.624 ms
- Canonical output: `{"approved_asset_ids": ["NORTHSTAR-GB-CW01-VID-004"], "approved_blueprint": "northstar-test-blueprint", "approved_campaign_world": "northstar-test-world-a", "approved_creative_bible": "northstar-test-creative-bible", "audit_event": "campaign-engine validated", "campaign_id": "northstar-test-autumn-growth", "media_spend_authorised": false, "publication_authorised": false, "state": "asset_suite_approved"}`

### meta_read_ingestion — PASS

- Input: `{"campaign_id": "northstar-test-meta-campaign", "period": "7d"}`
- Provider / operation: `meta / get_performance`
- Validation: passed
- Resulting state: `performance_ingested`
- Audit event: `media-3c82c08dd42b4c61b2848e0c`
- Error: None
- Elapsed: 1.025 ms
- Canonical output: `{"audit_event": "media-3c82c08dd42b4c61b2848e0c", "campaign_id": "northstar-test-autumn-growth", "metrics": {"budget": {"attribution_context": "Meta 7-day click / 1-day view; provider attributed", "available": false, "currency": "GBP", "value": null}, "clicks": {"attribution_context": "Meta 7-day click / 1-day view; provider attributed", "available": true, "currency": null, "value": "9100"}, "conversion_value": {"attribution_context": "Meta 7-day click / 1-day view; provider attributed", "available": true, "currency": "GBP", "value": "15400"}, "conversions": {"attribution_context": "Meta 7-day click / 1-day view; provider attributed", "available": true, "currency": null, "value": "140"}, "cpa": {"attribution_context": "Meta 7-day click / 1-day view; provider attributed", "available": true, "currency": "GBP", "value": "25"}, "cpc": {"attribution_context": "Meta 7-day click / 1-day view; provider attributed", "available": true, "currency": "GBP", "value": "0.38"}, "cpm": {"attribution_context": "Meta 7-day click / 1-day view; provider attributed", "available": true, "currency": "GBP", "value": "7.95"}, "ctr": {"attribution_context": "Meta 7-day click / 1-day view; provider attributed", "available": true, "currency": null, "value": "2.07"}, "frequency": {"attribution_context": "Meta 7-day click / 1-day view; provider attributed", "available": true, "currency": null, "value": "1.76"}, "impressions": {"attribution_context": "Meta 7-day click / 1-day view; provider attributed", "available": true, "currency": null, "value": "440000"}, "reach": {"attribution_context": "Meta 7-day click / 1-day view; provider attributed", "available": true, "currency": null, "value": "250000"}, "roas": {"attribution_context": "Meta 7-day click / 1-day view; provider attributed", "available": true, "currency": null, "value": "4.4"}, "spend": {"attribution_context": "Meta 7-day click / 1-day view; provider attributed", "available": true, "currency": "GBP", "value": "3500"}, "video_completions": {"attribution_context": "Meta 7-day click / 1-day view; provider attributed", "available": true, "currency": null, "value": "52000"}, "video_views": {"attribution_context": "Meta 7-day click / 1-day view; provider attributed", "available": true, "currency": null, "value": "180000"}}, "provider": "meta", "state": "performance_ingested"}`

### tiktok_read_ingestion — PASS

- Input: `{"campaign_id": "northstar-test-tiktok-campaign", "period": "7d"}`
- Provider / operation: `tiktok / get_performance`
- Validation: passed
- Resulting state: `performance_ingested`
- Audit event: `media-72168d10b083f67a26346aae`
- Error: None
- Elapsed: 0.882 ms
- Canonical output: `{"audit_event": "media-72168d10b083f67a26346aae", "campaign_id": "northstar-test-autumn-growth", "metrics": {"budget": {"attribution_context": "TikTok 7-day click / 1-day view; provider attributed", "available": false, "currency": "GBP", "value": null}, "clicks": {"attribution_context": "TikTok 7-day click / 1-day view; provider attributed", "available": true, "currency": null, "value": "8700"}, "conversion_value": {"attribution_context": "TikTok 7-day click / 1-day view; provider attributed", "available": true, "currency": "GBP", "value": "2925"}, "conversions": {"attribution_context": "TikTok 7-day click / 1-day view; provider attributed", "available": true, "currency": null, "value": "75"}, "cpa": {"attribution_context": "TikTok 7-day click / 1-day view; provider attributed", "available": true, "currency": "GBP", "value": "52"}, "cpc": {"attribution_context": "TikTok 7-day click / 1-day view; provider attributed", "available": true, "currency": "GBP", "value": "0.45"}, "cpm": {"attribution_context": "TikTok 7-day click / 1-day view; provider attributed", "available": true, "currency": "GBP", "value": "6.5"}, "ctr": {"attribution_context": "TikTok 7-day click / 1-day view; provider attributed", "available": true, "currency": null, "value": "1.45"}, "frequency": {"attribution_context": "TikTok 7-day click / 1-day view; provider attributed", "available": true, "currency": null, "value": "1.46"}, "impressions": {"attribution_context": "TikTok 7-day click / 1-day view; provider attributed", "available": true, "currency": null, "value": "600000"}, "reach": {"attribution_context": "TikTok 7-day click / 1-day view; provider attributed", "available": true, "currency": null, "value": "410000"}, "roas": {"attribution_context": "TikTok 7-day click / 1-day view; provider attributed", "available": true, "currency": null, "value": "0.75"}, "spend": {"attribution_context": "TikTok 7-day click / 1-day view; provider attributed", "available": true, "currency": "GBP", "value": "3900"}, "video_completions": {"attribution_context": "TikTok 7-day click / 1-day view; provider attributed", "available": true, "currency": null, "value": "80000"}, "video_views": {"attribution_context": "TikTok 7-day click / 1-day view; provider attributed", "available": true, "currency": null, "value": "350000"}}, "provider": "tiktok", "state": "performance_ingested"}`

### google_read_ingestion — PASS

- Input: `{"campaign_id": "northstar-test-google-campaign", "period": "7d"}`
- Provider / operation: `google / get_performance`
- Validation: passed
- Resulting state: `performance_ingested`
- Audit event: `media-982f6a6f71619800e52a76b3`
- Error: None
- Elapsed: 1.043 ms
- Canonical output: `{"audit_event": "media-982f6a6f71619800e52a76b3", "campaign_id": "northstar-test-autumn-growth", "metrics": {"budget": {"attribution_context": "Google Ads data-driven attribution; provider attributed", "available": false, "currency": "GBP", "value": null}, "clicks": {"attribution_context": "Google Ads data-driven attribution; provider attributed", "available": true, "currency": null, "value": "5200"}, "conversion_value": {"attribution_context": "Google Ads data-driven attribution; provider attributed", "available": false, "currency": "GBP", "value": null}, "conversions": {"attribution_context": "Google Ads data-driven attribution; provider attributed", "available": false, "currency": null, "value": null}, "cpa": {"attribution_context": "Google Ads data-driven attribution; provider attributed", "available": false, "currency": "GBP", "value": null}, "cpc": {"attribution_context": "Google Ads data-driven attribution; provider attributed", "available": true, "currency": "GBP", "value": "0.40"}, "cpm": {"attribution_context": "Google Ads data-driven attribution; provider attributed", "available": true, "currency": "GBP", "value": "11.05"}, "ctr": {"attribution_context": "Google Ads data-driven attribution; provider attributed", "available": true, "currency": null, "value": "2.74"}, "frequency": {"attribution_context": "Google Ads data-driven attribution; provider attributed", "available": false, "currency": null, "value": null}, "impressions": {"attribution_context": "Google Ads data-driven attribution; provider attributed", "available": true, "currency": null, "value": "190000"}, "reach": {"attribution_context": "Google Ads data-driven attribution; provider attributed", "available": false, "currency": null, "value": null}, "roas": {"attribution_context": "Google Ads data-driven attribution; provider attributed", "available": false, "currency": null, "value": null}, "spend": {"attribution_context": "Google Ads data-driven attribution; provider attributed", "available": true, "currency": "GBP", "value": "2100"}, "video_completions": {"attribution_context": "Google Ads data-driven attribution; provider attributed", "available": false, "currency": null, "value": null}, "video_views": {"attribution_context": "Google Ads data-driven attribution; provider attributed", "available": false, "currency": null, "value": null}}, "provider": "google", "state": "performance_ingested"}`

### restart_recovery — PASS

- Input: `{"restart": true}`
- Provider / operation: `all / replay_execution_journal`
- Validation: passed
- Resulting state: `recovered`
- Audit event: `921a35164e50d717a355bd2e055f205a190eef3d425896940aea21409ac9474b`
- Error: None
- Elapsed: 0.695 ms
- Canonical output: `{"audit_event": "921a35164e50d717a355bd2e055f205a190eef3d425896940aea21409ac9474b", "snapshot_count": 3, "state": "recovered"}`

### analysis_and_recommendation — PASS

- Input: `{"snapshot_count": 3}`
- Provider / operation: `all / analyse`
- Validation: passed
- Resulting state: `recommendations_pending_human_review`
- Audit event: `derived_from_audited_snapshots`
- Error: None
- Elapsed: 0.394 ms
- Canonical output: `{"audit_event": "derived_from_audited_snapshots", "recommendations": [{"category": "high_performer", "severity": "info"}, {"category": "creative_rejected", "severity": "critical"}, {"category": "overspend_risk", "severity": "high"}, {"category": "poor_performer", "severity": "high"}, {"category": "tracking", "severity": "critical"}], "state": "recommendations_pending_human_review"}`

### tony_report — PASS

- Input: `{"interface": "Tony"}`
- Provider / operation: `all / /media northstar-test-co 7d`
- Validation: passed
- Resulting state: `attention_required`
- Audit event: `read_only_query`
- Error: None
- Elapsed: 0.521 ms
- Canonical output: `{"audit_event": "read_only_query", "data": {"external_action_taken": false, "human_approval_required": true, "mode": "7d", "provider_count": 3, "recommendation_categories": ["high_performer", "creative_rejected", "overspend_risk", "poor_performer", "tracking"], "total_spend": "9500", "total_spend_currency": "GBP"}, "message": "3 verified provider snapshot(s); 5 recommendation(s); 2 critical. No media mutation or spend action was taken.", "state": "attention_required"}`

### phase_one_write_prohibition — PASS

- Input: `{"approval_id": "northstar-test-matt-approval"}`
- Provider / operation: `meta / activate_campaign`
- Validation: passed
- Resulting state: `blocked`
- Audit event: `media-9688165acaaac5ecac464a76`
- Error: None
- Elapsed: 0.643 ms
- Canonical output: `{"audit_event": "media-9688165acaaac5ecac464a76", "provider_calls_added": 0, "state": "blocked"}`

## Integrity and cleanup

- Journal verification: `{"decisions": 1, "head_hash": "4bbab0e12886981c162b5b512bca5fe541a80871e39b1540b72df285fa238516", "ok": true, "records": 4}`
- Orphaned artefacts: `[]`
- State inconsistencies: `[]`
- Production records modified: `false`

## Fixture exceptions detected

- Meta: high performer.
- TikTok: rejected creative, poor performer and overspend risk.
- Google: missing tracking and deliberately unavailable conversion metrics retained as null.
- Provider/API failure and expired-credential behaviour are covered by focused automated tests.

## Recommended fixes / next work

1. Complete external OAuth/app approval and connect production read transports one provider at a time.
2. Add n8n schedules only after each provider passes a live read-only smoke test.
3. Keep every mutation method disabled until a separately reviewed activation phase introduces approval-bound execution.
