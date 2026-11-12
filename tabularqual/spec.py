from __future__ import annotations
# version
VERSION = "0.1.7"

# sheet names
SHEET_MODEL = "Model"
SHEET_SPECIES = "Species"
SHEET_TRANSITIONS = "Transitions"
SHEET_INTERACTIONS = "Interactions"  # optional

# Model sheet columns
MODEL_ID = "Model_ID"
MODEL_NAME = "Name"
MODEL_SOURCE = "Model_source"
MODEL_PUBLICATION = "Publication"
MODEL_ORIGIN_PUBLICATION = "Origin_publication"
MODEL_ORIGIN_MODEL = "Origin_model"
MODEL_TAXON = "Taxon"
MODEL_BIOLOGICAL_PROCESS = "Biological_process"
MODEL_CREATED = "Created"
MODEL_MODIFIED = "Modified"
MODEL_CREATOR_PREFIX = "Creator"
MODEL_CONTRIBUTOR_PREFIX = "Contributor"
MODEL_VERSION = "Version"
MODEL_NOTES_PREFIX = "Notes"

# Species sheet columns
SPECIES_ID = "Species_ID"
SPECIES_NAME = "Name"
SPECIES_RELATION_PREFIX = "Relation"
SPECIES_IDENTIFIER_PREFIX = "Identifier"
SPECIES_COMPARTMENT = "Compartment"
SPECIES_TYPE = "Type"  # Input/Internal/Output
SPECIES_CONSTANT = "Constant"
SPECIES_INITIAL_LEVEL = "InitialLevel"
SPECIES_MAX_LEVEL = "MaxLevel"
SPECIES_NOTES_PREFIX = "Notes"
COMMENTS_COL = "Comments"

# Interactions sheet columns (optional)
INTER_TARGET = "Target"
INTER_SOURCE = "Source"
INTER_SIGN = "Sign"  # positive, negative, dual, unknown
INTER_RELATION_PREFIX = "Relation"
INTER_IDENTIFIER_PREFIX = "Identifier"
INTER_NOTES_PREFIX = "Notes"

# Transitions sheet columns
TRANSITION_ID = "Transitions_ID"
TRANSITION_NAME = "Name"
TRANSITION_TARGET = "Target"
TRANSITION_LEVEL = "Level"
TRANSITION_RULE = "Rule"
TRANSITION_RELATION_PREFIX = "Relation"
TRANSITION_IDENTIFIER_PREFIX = "Identifier"
TRANSITION_NOTES_PREFIX = "Notes"

# Default compartment name if none provided
DEFAULT_COMPARTMENT = "default"

# TODO: check for invalid symbols in the spreadsheet
# Allowed boolean symbols
SYMBOL_AND = "&"
SYMBOL_OR = "|"
SYMBOL_NOT = "!"
SYMBOL_GE = ">="
SYMBOL_LE = "<="
SYMBOL_GT = ">"
SYMBOL_LT = "<"
SYMBOL_EQ = "="
SYMBOL_NEQ = "!="
SYMBOL_XOR = "^"
SYMBOL_COLON = ":"

# valid values
SYMBOLS = [SYMBOL_AND, SYMBOL_OR, SYMBOL_NOT, SYMBOL_XOR, SYMBOL_GE, SYMBOL_LE, SYMBOL_GT, SYMBOL_LT, SYMBOL_EQ, SYMBOL_NEQ, SYMBOL_COLON]
RELATIONS_BQBIOL = ["is", "hasVersion", "isVersionOf", "isDescribedBy", "hasPart", "isPartOf", "hasProperty", "isPropertyOf", "encodes", "isEncodedBy", "isHomologTo", "occursIn", "hasTaxon"]
RELATIONS_BQMODEL = ["is", "isDerivedFrom", "isDescribedBy", "isInstanceOf", "hasInstance"]
TYPES = ["Input", "Internal", "Output"]
SIGN = ["positive", "negative", "dual", "unknown"]

# Case-insensitive lookup maps for normalization
_RELATIONS_BQBIOL_LOWER = {rel.lower(): rel for rel in RELATIONS_BQBIOL}
_RELATIONS_BQMODEL_LOWER = {rel.lower(): rel for rel in RELATIONS_BQMODEL}
_TYPES_LOWER = {typ.lower(): typ for typ in TYPES}
_SIGN_LOWER = {sign.lower(): sign for sign in SIGN}


def normalize_relation_bqbiol(input_rel: str) -> str | None:
    if not input_rel:
        return None
    return _RELATIONS_BQBIOL_LOWER.get(input_rel.lower())


def normalize_type(input_type: str) -> str | None:
    if not input_type:
        return None
    return _TYPES_LOWER.get(input_type.lower())


def normalize_sign(input_sign: str) -> str | None:
    if not input_sign:
        return None
    return _SIGN_LOWER.get(input_sign.lower())


def is_repeated_column(column_name: str, prefix: str) -> bool:
    if not column_name.startswith(prefix):
        return False
    # Accept exact or numeric suffix like Relation2, Identifier10
    if column_name == prefix:
        return True
    suffix = column_name[len(prefix):]
    return suffix.isdigit() and len(suffix) > 0
