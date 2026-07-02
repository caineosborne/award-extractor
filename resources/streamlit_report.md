# Streamlit QA Report

Date: 2026-07-02

Scope:
- Streamlit app at `streamlit_review/app.py`
- Clean UI-driven run for `MA000120`
- Consequence branch run from `3.1` onward

## Section Results

- Launch: PASS
- End-to-End Pipeline: PASS with warnings
- Screen Validation: PASS with test-harness validation
- Manual Review Step 4B: PASS for existing flow, not exhaustively exercised during this pass
- Cohort Coverage: PASS for the supported MA000120 consequence and creation outputs available in the app
- Navigation: PASS for the controls exercised in the Streamlit test harness

## Findings

### 1. High severity: consequence `3.1` path was broken
- Reproduction: In the Streamlit app, select `MA000120`, switch `Step 3 ruleset` to `Overtime consequence`, then click `Generate overtime ruleset`.
- Result: The run failed immediately with `ValueError: Unsupported overtime ruleset: overtime_consequence`.
- Probable cause: `src/step_3_1_generate_ruleset/core.py` only resolved the step 3.1 output path for `overtime_creation`.
- Fix: Updated `interpretation_output_path_for_source()` to resolve `overtime_consequence` to `3_1_OT_consequence_ruleset.md`. Added a regression test in `tests/test_award_pipeline.py`.
- Status: Resolved.

### 2. Medium severity: consequence `3.2` required a creator-response validation retry
- Reproduction: Run the Streamlit consequence workflow from `3.1` through `3.2`.
- Result: The first creator response failed validation, then the pipeline automatically requested one corrected response and completed successfully.
- Probable cause: The model output did not satisfy the review validator on the first pass.
- Suggested fix: Review the consequence review prompt and validation rules if this becomes frequent. At present this is non-blocking and the pipeline recovers automatically.
- Status: Completed with retry, not a crash.

### 3. Medium severity: consequence `5.1` completed with validation issues
- Reproduction: Continue the Streamlit consequence workflow through `5.1`.
- Result: The run completed and wrote `5_1_OT_consequence_pseudocode.md`, but the status ended as `warning` with validation issues.
- Probable cause: Deterministic pseudocode validation found missing coverage, then the step repaired once and still finished with a warning summary.
- Suggested fix: Review the consequence pseudocode source and the validation coverage rules if this warning is not acceptable for release.
- Status: Present in the final run output.

'### 4. Low severity / enhancement: subset selection is still single-select
- Request: Add a dropdown or tick-box control so the user can choose the ruleset subset combination to run, instead of only choosing one ruleset at a time.
- Current state: Not implemented in the Streamlit UI.
- Suggested fix: Replace the current single `Step 3 ruleset` selector with a multi-select checkbox control that can include creation, consequence, or both.
- Status: Enhancement request only.'

### 5. Not reproduced in test harness: output-set dropdown visibility
- Observation: In the Streamlit test harness, the `Load existing output set` dropdown includes `MA000120`, `MA000120_e2e_cli_check`, and `MA000120_e2e_qa_20260702`.
- Note: I could not reproduce the claim that only `MA000120_e2e_cli_check` is available.
- Suggested check: If the live browser still shows only one entry, refresh the session and confirm the app is reading `data/processed/*/2_1_payment_classification.json` from the current workspace.

User udpate - this worked upon refresh - what is the trigger for an award to get into the drop down? 

### 5 -  the OT clause classification doesn't take the shared file - it looks for the specific one that doesn't exist. 


Displayed file: data/processed/MA000120/2_2_OT_consequence_clause_classification.json
Last modified: File not found
File not found: data/processed/MA000120/2_2_OT_consequence_clause_classification.json


###6 - Stremlit error

```  2028 │   │   │   else f"{label}_{abs(hash(rendered_json))}_json_view"               
    2029 │   │   )                                                                      
  ❱ 2030 │   │   st.text_area(                                                          
    2031 │   │   │   label,                                                             
    2032 │   │   │   value=rendered_json,                                               
    2033 │   │   │   height=widget_height,                                              
                                                                                        
  /Users/caineosborne/Projects2026/award-extractor/.venv/lib/python3.12/site-packages/  
  streamlit/runtime/metrics_util.py:698 in wrapped_func                                 
                                                                                        
  /Users/caineosborne/Projects2026/award-extractor/.venv/lib/python3.12/site-packages/  
  streamlit/elements/widgets/text_widgets.py:697 in text_area                           
                                                                                        
  /Users/caineosborne/Projects2026/award-extractor/.venv/lib/python3.12/site-packages/  
  streamlit/elements/widgets/text_widgets.py:746 in _text_area                          
                                                                                        
  /Users/caineosborne/Projects2026/award-extractor/.venv/lib/python3.12/site-packages/  
  streamlit/elements/lib/utils.py:261 in compute_and_register_element_id                
                                                                                        
  /Users/caineosborne/Projects2026/award-extractor/.venv/lib/python3.12/site-packages/  
  streamlit/elements/lib/utils.py:143 in _register_element_id                           
────────────────────────────────────────────────────────────────────────────────────────
StreamlitDuplicateElementKey: There are multiple elements with the same `key='Structured
overtime rules 
JSON_/Users/caineosborne/Projects2026/award-extractor/data/processed/MA000120/3_1_OT_cre
ation_ruleset.json_6416849211696422160_json_view'`. To fix this, please make sure that 
the `key` argument is unique for each element you create.
ç
```


## Verified Artifacts

- `data/processed/MA000120/1_2_award.json`
- `data/processed/MA000120/2_1_payment_classification.json`
- `data/processed/MA000120/2_2_OT_creation_clause_classification.json`
- `data/processed/MA000120/3_1_OT_creation_ruleset.md`
- `data/processed/MA000120/3_2_OT_creation_revised_ruleset.md`
- `data/processed/MA000120/4_1_OT_creation_formatted_ruleset.md`
- `data/processed/MA000120/5_1_OT_creation_pseudocode.md`
- `data/processed/MA000120/3_1_OT_consequence_ruleset.md`
- `data/processed/MA000120/3_2_OT_consequence_revised_ruleset.md`
- `data/processed/MA000120/4_1_OT_consequence_formatted_ruleset.md`
- `data/processed/MA000120/5_1_OT_consequence_pseudocode.md`

## Notes

- The consequence `5.1` run finished with a validation warning, not a crash.
- The Streamlit app run completed successfully for both the creation and consequence branches.
- The browser automation surface in this environment was not available, so UI checks were performed with Streamlit's test harness and the app's own status/log files.
