# Engineering Artifact Ingestion Demo

## Scenario

1. Run a dry-run parse:
   `python manage.py ingest_engineering_artifacts --root docs --limit 5 --dry-run --json`.
2. For a stronger demo, pass a P-CAD `.drc/.erc/.net` file or a DXF file. The command normalizes it into `EngineeringArtifact` facts.
3. Closed binary files such as DWG and MS14 are not silently “understood”: DOLG stores metadata and a conversion warning.
4. Run or open Engineering Review for the linked project. Imported CAD findings appear in `external_cad`, affect score and get Russian fields: `title_ru`, `evidence_ru`, `recommendation_ru`.
5. Open Self AI and ask why the check failed. The assistant uses artifact memory, review findings and fault cases as evidence.
6. Show learning-by-artifact: a DRC error becomes a practical task with source file, expected fix and verification rubric.

## Safe Self-Learning Position

The neural layer must not train during a live answer. The safe loop is:

1. Collect artifact facts, user corrections, review findings and fault cases.
2. Validate examples manually or through expert rules.
3. Periodically retrain the PyTorch deep-hint model.
4. Keep fallback to expert rules and human control for the final engineering verdict.
