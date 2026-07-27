from tabularqual.identifiers import (
    normalize_compact_identifier,
    to_identifiers_url,
    url_to_compact_identifier,
)
from tabularqual.sbml_writer import write_sbml
from tabularqual.types import ModelInfo, QualModel, Species


def test_chebi_compact_identifier_capitalization_is_normalized():
    assert normalize_compact_identifier("chebi:35305") == "CHEBI:35305"
    assert normalize_compact_identifier("ChEbI:35305") == "CHEBI:35305"
    assert normalize_compact_identifier("CHEBI:35305") == "CHEBI:35305"


def test_chebi_uri_variants_are_normalized_without_changing_other_prefixes():
    assert (
        to_identifiers_url("chebi:35305")
        == "https://identifiers.org/CHEBI:35305"
    )
    assert (
        to_identifiers_url("https://identifiers.org/chebi:35305")
        == "https://identifiers.org/CHEBI:35305"
    )
    assert (
        to_identifiers_url("urn:miriam:chebi:35305")
        == "urn:miriam:CHEBI:35305"
    )
    assert (
        to_identifiers_url("uniprot:P19838")
        == "https://identifiers.org/uniprot:P19838"
    )


def test_chebi_round_trip_uses_canonical_curie():
    canonical_uri = "https://identifiers.org/CHEBI:35305"
    assert url_to_compact_identifier(
        "https://identifiers.org/chebi:35305"
    ) == "CHEBI:35305"
    assert url_to_compact_identifier(canonical_uri) == "CHEBI:35305"


def test_sbml_writer_emits_canonical_chebi_resource():
    model = QualModel(
        model=ModelInfo(model_id="annotation_test"),
        species={
            "S": Species(
                species_id="S",
                annotations=[("is", "chebi:35305")],
            )
        },
        transitions=[],
    )

    sbml, warnings = write_sbml(model, print_messages=False)

    assert warnings == []
    assert 'rdf:resource="https://identifiers.org/CHEBI:35305"' in sbml
    assert 'rdf:resource="https://identifiers.org/chebi:35305"' not in sbml
