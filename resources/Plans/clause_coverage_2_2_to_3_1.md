# First-pass clause coverage: step 2.2 to step 3.1

## Summary

Add a granular clause-coverage ledger for the overtime-creation path only. Step 2.2 deterministically expands its generation-ready clause selection into the lowest source nodes with their own text, preserving parent text as inherited context. The existing final 3.1 expert-comparison call returns one treatment decision per expanded clause.

Configure the existing 3.1 drafting and comparison calls for `gpt-5.6-luna` with low reasoning effort, subject to verifying that the pipeline's Responses API deployment supports that model identifier and setting. Do not add a separate lineage-model call.

The final coverage outcomes are:

- **Included**: mapped to one or more final rules, with a role such as `operative`, `condition`, `exception`, `scope`, or `supporting_context`.
- **Explicitly excluded**: not used in the overtime-creation ruleset, with a required reason.
- **Unexplained**: assigned deterministically where no valid inclusion mapping or explicit exclusion exists.

## Implementation changes

- Extend the 2.2 artifact with a deterministic overtime-creation source population:
  - Start with existing 2.2 classifications that feed overtime creation.
  - Reload the parsed award identified by the step 2.1 artifact and expand each selected clause tree.
  - Record the lowest node containing its own substantive text; heading-only ancestors are inherited context rather than separate ledger items.
  - Retain stable clause ID, source text, ordered parent path, inherited parent text, originating 2.2 classification, and scope tags.

- Keep the expanded source text compact in the 3.1 prompt:
  - Supply each granular source item once, with its clause ID and inherited context.
  - Avoid repeating full parent text under every child where a shared hierarchy block can express it.
  - Require granular source IDs in final rules' `source_clause_numbers`.

- Extend only the final comparison response with `clause_dispositions`:
  - Included records contain the source ID and final rule mappings with a mapping role.
  - Excluded records contain the source ID and a specific reason.
  - The comparison prompt treats this mapping as a reconciliation task after merging rules, not a second extraction task.
  - Keep included records terse; require free-text explanation only for exclusions.

- Add deterministic coverage validation after final merge:
  - Validate IDs, uniqueness, mapping roles, final rule references, and exclusion reasons.
  - Confirm each included source clause is cited by every mapped final rule.
  - Convert missing, duplicate, unknown, or inconsistent dispositions into **Unexplained** records and validation warnings.
  - Save the complete ledger in the final 3.1 JSON artifact.

- Add a concise "Clause coverage" section to final 3.1 markdown with totals and details for excluded and unexplained clauses.

- Make reasoning effort configurable, defaulting to `low`, alongside the selected model. Fail clearly if the configured model does not accept the requested setting.

- Require the new 2.2 artifact schema version for granular coverage. Older artifacts must be regenerated rather than silently falling back to L2-level tracking.

## Test plan

- Test nested numeric and lettered expansion, inherited context, substantive parent text, and heading-only parents.
- Test compact prompt construction without lost source context.
- Test many-to-many mappings and supporting-context mappings.
- Test explicit exclusions, missing dispositions, unknown IDs, duplicate IDs, and rule-inconsistent mappings.
- Test JSON and markdown counts and details match.
- Test the default low-reasoning request configuration and its clear failure path for unsupported model settings.

## Assumptions

- This first pass changes only overtime creation from 2.2 through final 3.1 output.
- "Lowest appropriate level" means the lowest node containing its own substantive text.
- Deterministic code owns population, validation, and reporting; the LLM owns semantic inclusion and exclusion judgement.
