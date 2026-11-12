import re
from pathlib import Path

import pytest

from tabularqual import convert_spreadsheet_to_sbml
from tabularqual.sbml_writer import write_sbml
from tabularqual.types import ModelInfo, QualModel, Species, Transition


def _write_csvs(directory: Path, prefix: str, species: str, transitions: str) -> None:
    (directory / f"{prefix}_Model.csv").write_text(
        "Model_source,link.to.the.model.com\n"
        f"Model_ID,{prefix}\n"
        "Name,Minimal reproducible example\n",
        encoding="utf-8",
    )
    (directory / f"{prefix}_Species.csv").write_text(species, encoding="utf-8")
    (directory / f"{prefix}_Transitions.csv").write_text(transitions, encoding="utf-8")


def _ci_names(sbml: str) -> list[str]:
    return re.findall(r"<ci>\s*([^<]+?)\s*</ci>", sbml)


def test_digit_prefixed_species_id_is_rewritten_inside_rules(tmp_path):
    species = (
        "Species_ID,Name,Compartment,Type,Constant,InitialLevel,MaxLevel\n"
        "2A,GeneA,cytosol,Internal,False,0,1\n"
        "B,GeneB,cytosol,Internal,False,0,1\n"
    )
    transitions = (
        "Transitions_ID,Name,Target,Level,Rule\n"
        "tr_2A,GeneA activation,2A,1,B\n"
        "tr_B,GeneB activation,B,1,2A\n"
    )
    _write_csvs(tmp_path, "MRE", species, transitions)
    out = tmp_path / "MRE.sbml"

    stats = convert_spreadsheet_to_sbml(
        str(tmp_path), str(out), print_messages=False, validate=False
    )

    sbml = out.read_text(encoding="utf-8")
    assert "_2A" in _ci_names(sbml)
    assert "2A" not in _ci_names(sbml)
    assert sbml.count('qualitativeSpecies="_2A"') >= 2
    assert any(
        "rule reference '2A'" in warning and "_2A" in warning
        for warning in stats["warnings"]
    )

    threshold = tmp_path / "threshold"
    threshold.mkdir()
    _write_csvs(
        threshold,
        "THR",
        "Species_ID,Name,Compartment,Type,Constant,InitialLevel,MaxLevel\n"
        "A,GeneA,cytosol,Internal,False,0,1\n"
        "B,GeneB,cytosol,Internal,False,0,1\n",
        "Transitions_ID,Name,Target,Level,Rule\n"
        "tr_A,GeneA activation,A,1,B >= 1\n",
    )
    thr_out = threshold / "THR.sbml"
    convert_spreadsheet_to_sbml(
        str(threshold), str(thr_out), print_messages=False, validate=False
    )
    assert _ci_names(thr_out.read_text(encoding="utf-8")) == ["B"]


def test_unknown_rule_species_is_an_error():
    model = QualModel(
        model=ModelInfo(model_id="m"),
        species={"A": Species(species_id="A")},
        transitions=[
            Transition(
                transition_id="tr_A",
                name=None,
                target="A",
                level=1,
                rule="Nope",
            )
        ],
    )
    with pytest.raises(ValueError, match="unknown species: Nope"):
        write_sbml(model, print_messages=False)
