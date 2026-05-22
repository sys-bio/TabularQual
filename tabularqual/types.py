from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Person:
    family_name: Optional[str] = None
    given_name: Optional[str] = None
    organization: Optional[str] = None
    email: Optional[str] = None


@dataclass
class ModelInfo:
    model_id: str
    name: Optional[str] = None
    source_urls: List[str] = field(default_factory=list)
    described_by: List[str] = field(default_factory=list)
    derived_from: List[str] = field(default_factory=list)
    biological_processes: List[str] = field(default_factory=list)
    taxons: List[str] = field(default_factory=list)
    created_iso: Optional[str] = None
    modified_iso: Optional[str] = None
    creators: List[Person] = field(default_factory=list)
    contributors: List[Person] = field(default_factory=list)
    versions: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    # list of (qualifier, identifier) for other qualifiers
    other_annotations: List[Tuple[str, str]] = field(default_factory=list)


@dataclass
class Species:
    species_id: str
    name: Optional[str] = None
    compartment: Optional[str] = None
    constant: Optional[bool] = None
    initial_level: Optional[int] = None
    max_level: Optional[int] = None
    type: Optional[str] = None  # Input/Internal/Output
    # list of (qualifier, identifier)
    annotations: List[Tuple[str, str]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    comments: Optional[str] = None


@dataclass
class InteractionEvidence:
    target: str
    source: str
    sign: Optional[str] = None
    annotations: List[Tuple[str, str]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    comments: Optional[str] = None


@dataclass
class Transition:
    transition_id: Optional[str]
    name: Optional[str]
    target: str
    level: Optional[int]  # resultLevel
    rule: str  # boolean expression string
    annotations: List[Tuple[str, str]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    comments: Optional[str] = None


@dataclass
class QualModel:
    model: ModelInfo
    species: Dict[str, Species]
    transitions: List[Transition]
    interactions: List[InteractionEvidence] = field(default_factory=list)