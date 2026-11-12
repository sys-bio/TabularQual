# Changelog

All notable changes to TabularQual are documented here.

## 0.1.7 - 2026-11-12

### Fixed

- Rewrite digit-prefixed species IDs inside transition rules. A Species_ID
  such as `2A` is cleaned to `_2A` on the species sheet and as a transition
  target; the same cleaned ID is now substituted in Rule expressions, so the
  generated SBML math and inputs refer to `_2A`.
- Fail conversion when a rule names a species that is not in the model,
  instead of omitting that input and writing SBML that does not match the rule.

### Changed

- Move Streamlit and pandas out of the core install into an `app` extra.
  `pip install tabularqual` is the CLI and Python API. `pip install tabularqual[app]`
  adds the web app.
- Require sbmlutils 0.10.2 or newer and python-libsbml 5.21.1 or newer, so the
  core install no longer pulls in libroadrunner, matplotlib, py4cytoscape, or cobra.
- Drop the unused packaging dependency.

## 0.1.6 - 2026-07-26

### Fixed

- Normalize common ChEBI annotation forms such as `chebi:35305` to the
  validator-compatible `CHEBI:35305` CURIE.
- Preserve normalized ChEBI identifiers across SBML and spreadsheet
  round-trips.
- Repair FastAPI XLSX responses that referenced an undefined output variable.
- Clean up API job directories reliably and reject unsafe or duplicate upload
  filenames.
- Prevent the manual BioDivine benchmark script from being collected by
  pytest.
- Package the default spreadsheet template and exclude benchmark/test modules
  from the wheel.

### Changed

- Document the Python 3.11-or-newer environment and declare API, test, and
  release extras.
- Modernize PyPI metadata and release tooling.
