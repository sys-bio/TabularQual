from __future__ import annotations

from typing import List, Tuple, Dict
from datetime import datetime, timezone
import re
import libsbml
import gc

from . import spec
from .types import QualModel, Species as SpeciesT, Transition as TransitionT
from .expr_parser import parse as parse_expr, ast_to_mathml
from .identifiers import to_identifiers_url


def _resolve_name_to_id(name_or_id: str, species: Dict[str, SpeciesT]) -> str:
    """Resolve a name (possibly quoted, or with suffix) or ID to a species ID.
    
    Args:
        name_or_id: Either a species name (possibly quoted, or with suffix) or ID
        species: Dict of species by ID
        
    Returns:
        The species ID
    """
    # Remove quotes if present
    if name_or_id.startswith('"') and name_or_id.endswith('"'):
        name_or_id = name_or_id[1:-1]
    
    # First try as ID
    if name_or_id in species:
        return name_or_id
    
    # Check if it's a name with suffix (e.g., "GeneA_1")
    match = re.match(r'^(.+)_(\d+)$', name_or_id)
    if match:
        base_name = match.group(1)
        suffix_num = int(match.group(2))
        # Find species with this base name and match by occurrence
        matching_species = [(sid, sp) for sid, sp in species.items() if sp.name == base_name]
        if matching_species and suffix_num > 0:
            occurrence_index = suffix_num  # suffix_num 1 → occurrence index 1, suffix_num 2 → occurrence index 2
            if occurrence_index < len(matching_species):
                return matching_species[occurrence_index][0]
    
    # Try as name without suffix (reverse lookup)
    for sid, sp in species.items():
        if sp.name == name_or_id:
            return sid
    
    # Not found, return as-is (will cause error later)
    return name_or_id


def _resolve_rule_names_to_ids(rule: str, species: Dict[str, SpeciesT]) -> str:
    """Resolve species names (possibly quoted, possibly with suffix) in a rule to IDs.
    
    Args:
        rule: The transition rule string (may contain quoted names or names with suffixes)
        species: Dict of species by ID
        
    Returns:
        Rule with names replaced by IDs
    """
    result = rule
    
    # Create mappings from name to IDs (handling duplicates)
    name_to_ids_map: Dict[str, List[Tuple[str, int]]] = {}
    for sid, sp in species.items():
        if sp.name:
            if sp.name not in name_to_ids_map:
                name_to_ids_map[sp.name] = []
            occurrence = len(name_to_ids_map[sp.name])  # 0 for first, 1 for second, 2 for third, etc.
            name_to_ids_map[sp.name].append((sid, occurrence))
    
    # Replace quoted names (with or without suffix)
    for name, id_list in name_to_ids_map.items():
        # Pattern for quoted name: "name" or "name_1" or "name":2 (with colon notation)
        # First occurrence (no suffix)
        quoted_pattern = r'"' + re.escape(name) + r'"(?::(\d+))?'
        def replace_quoted_first(match):
            colon_part = match.group(1)
            sid = id_list[0][0] if id_list else name
            if colon_part:
                return f"{sid}:{colon_part}"
            return sid
        result = re.sub(quoted_pattern, replace_quoted_first, result)
        
        # Subsequent occurrences with suffix (e.g., "name_1", "name_2")
        for idx, (sid, occurrence) in enumerate(id_list):
            if occurrence > 0:  # Skip first occurrence (no suffix)
                suffix_num = occurrence  # occurrence 1 → suffix _1, occurrence 2 → suffix _2
                quoted_suffix_pattern = r'"' + re.escape(f"{name}_{suffix_num}") + r'"(?::(\d+))?'
                def replace_quoted_suffix(match):
                    colon_part = match.group(1)
                    if colon_part:
                        return f"{sid}:{colon_part}"
                    return sid
                result = re.sub(quoted_suffix_pattern, replace_quoted_suffix, result)
    
    # Replace unquoted names (with or without suffix)
    for name, id_list in name_to_ids_map.items():
        # First occurrence (no suffix)
        if len(id_list) == 1:
            # Unique name - replace if not valid SId
            sid = id_list[0][0]
            if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name):
                pattern = r'\b' + re.escape(name) + r'(?=\s|&|\||!|\(|\)|>=|<=|>|<|!=|=|:|$)'
                result = re.sub(pattern, sid, result)
        else:
            # Duplicate names - replace with suffixes
            for sid, occurrence in id_list:
                if occurrence == 0:
                    # First occurrence - only replace if not valid SId
                    if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name):
                        pattern = r'\b' + re.escape(name) + r'(?=\s|&|\||!|\(|\)|>=|<=|>|<|!=|=|:|$)'
                        result = re.sub(pattern, sid, result)
                else:
                    # Subsequent occurrences with suffix
                    suffix_num = occurrence  # occurrence 1 → suffix _1, occurrence 2 → suffix _2
                    name_with_suffix = f"{name}_{suffix_num}"
                    pattern = r'\b' + re.escape(name_with_suffix) + r'(?=\s|&|\||!|\(|\)|>=|<=|>|<|!=|=|:|$)'
                    result = re.sub(pattern, sid, result)
    
    return result


def write_sbml(model: QualModel, *, interactions_anno: bool = True, transitions_anno: bool = True, use_name: bool = False, print_messages: bool = True) -> Tuple[str, List[str]]:
    """
    Write a QualModel to SBML-qual format.
    
    Returns:
        Tuple of (sbml_string, warnings) where warnings is a list of warning messages.
    """
    warnings_list: List[str] = []
    doc = None
    try:
        ns = libsbml.QualPkgNamespaces(3, 1, 1)
        doc = libsbml.SBMLDocument(ns)
    except Exception:
        doc = libsbml.SBMLDocument(3, 1)
        try:
            qual_uri = libsbml.QualExtension.getXmlnsL3V1V1()
        except Exception:
            qual_uri = "http://www.sbml.org/sbml/level3/version1/qual/version1"
        if not doc.enablePackage(qual_uri, "qual", True):
            raise ValueError("Failed to enable qual package")

    m = doc.createModel()
    # Ensure required flag after enabling
    try:
        doc.setPackageRequired("qual", True)
    except Exception:
        pass
    m.setId(model.model.model_id)
    if model.model.name:
        m.setName(model.model.name)

    # Metaid generator
    meta_counter = 1
    def next_metaid() -> str:
        nonlocal meta_counter
        s = f"metaid_{meta_counter:07d}"
        meta_counter += 1
        return s

    # Model-level notes
    if model.model.notes:
        _append_notes(m, model.model.notes)
    if model.model.versions:
        _append_notes_concat(m, [
            v if v.startswith("Version:") else f"Version: {v}"
            for v in model.model.versions
        ])

    # Annotations for model
    if not m.isSetMetaId():
        m.setMetaId(next_metaid())
    _add_model_annotations(m, model, print_messages=print_messages)

    # Compartment(s)
    comp_names = set()
    for s in model.species.values():
        comp = s.compartment or spec.DEFAULT_COMPARTMENT
        comp_names.add(comp)
    if not comp_names:
        comp_names.add(spec.DEFAULT_COMPARTMENT)
    for cname in sorted(comp_names):
        c = m.createCompartment()
        c.setId(cname)
        c.setConstant(True)

    # Qual plugin
    qual_model = m.getPlugin("qual")
    if qual_model is None:
        raise ValueError("Qual plugin unavailable on model")

    # Species
    for s in model.species.values():
        qs = qual_model.createQualitativeSpecies()
        qs.setId(s.species_id)
        if not qs.isSetMetaId():
            qs.setMetaId(next_metaid())
        if s.name:
            qs.setName(s.name)
        qs.setCompartment(s.compartment or spec.DEFAULT_COMPARTMENT)
        if s.constant is not None:
            qs.setConstant(bool(s.constant))
        else: # constant attribute is required, default to False
            qs.setConstant(False)
        if s.initial_level is not None:
            qs.setInitialLevel(int(s.initial_level))
        if s.max_level is not None:
            qs.setMaxLevel(int(s.max_level))
        # Add notes (including type if present)
        notes_to_add = []
        if s.type:
            notes_to_add.append(f"Type: {s.type}")
        if s.notes:
            notes_to_add.extend(s.notes)
        if notes_to_add:
            _append_notes(qs, notes_to_add)
        if s.annotations:
            _add_annotations(qs, s.annotations, use_model=False, print_messages=print_messages)

    # Group transitions by target to handle multiple levels
    transitions_by_target: Dict[str, List[TransitionT]] = {}
    for t in model.transitions:
        if t.target not in transitions_by_target:
            transitions_by_target[t.target] = []
        transitions_by_target[t.target].append(t)

    # Get all species IDs
    known_species_ids = set(model.species.keys())

    # Transitions
    for target, target_transitions in transitions_by_target.items():
        # Create one transition per target species
        qt = qual_model.createTransition()
        
        # Resolve target name to ID if use_name=True
        target_id = _resolve_name_to_id(target, model.species) if use_name else target
        
        # Use the first transition's ID or generate one
        # Strip level suffix from transition ID (e.g., tr_Cro_2 -> tr_Cro)
        first_transition = target_transitions[0]
        if first_transition.transition_id:
            # Remove level suffix if present (e.g., _2, _3)
            base_id = first_transition.transition_id
            # Match pattern like tr_Cro_2 and extract tr_Cro
            match = re.match(r'^(.+)_(\d+)$', base_id)
            if match:
                base_id = match.group(1)
            qt.setId(base_id)
        else:
            qt.setId(f"tr_{target_id}")
            
        if not qt.isSetMetaId():
            qt.setMetaId(next_metaid())
        if first_transition.name:
            qt.setName(first_transition.name)
            
        # Outputs
        out = qt.createOutput()
        out.setQualitativeSpecies(target_id)
        out.setTransitionEffect(_qual_enum("QUAL_TRANSITION_EFFECT_ASSIGNMENT_LEVEL", 1))

        # Helper function to check if a rule is a constant (integer or TRUE/FALSE)
        def is_constant_rule(rule_str: str) -> tuple[bool, int]:
            """Check if rule is a constant. Returns (is_constant, level_value)."""
            rule_stripped = rule_str.strip()
            if rule_stripped.upper() == 'FALSE':
                return True, 0
            elif rule_stripped.upper() == 'TRUE':
                return True, 1
            else:
                try:
                    level = int(rule_stripped)
                    return True, level
                except ValueError:
                    return False, 0
        
        # Check if ALL transitions for this target are constants
        all_constant = True
        highest_const_level = 0
        for t in target_transitions:
            is_const, const_level = is_constant_rule(t.rule)
            if not is_const:
                all_constant = False
                break
            # Track highest level for multi-level constants
            if is_const:
                highest_const_level = max(highest_const_level, const_level)
        
        # If all transitions are constant, emit only defaultTerm at highest level
        # This applies to both single-level and multi-level cases
        if all_constant:
            # Create only defaultTerm with the highest constant level
            ft_default = qt.createDefaultTerm()
            ft_default.setResultLevel(highest_const_level)
            # No inputs, no function terms, no rule notes
            # Skip to annotations/notes section
        else:
            # Normal case: create function terms for each level (mixed or all non-constant)
            # Create defaultTerm (typically level 0)
            ft_default = qt.createDefaultTerm()
            ft_default.setResultLevel(0)
            
            # Collect all unique species IDs from all rules for this target
            all_species_ids = set()
            for t in target_transitions:
                # Skip constant rules
                is_const, _ = is_constant_rule(t.rule)
                if is_const:
                    continue
                    
                # Resolve rule names to IDs if use_name=True
                rule = _resolve_rule_names_to_ids(t.rule, model.species) if use_name else t.rule
                ast = parse_expr(rule, known_species_ids)
                all_species_ids.update(_collect_ids_from_ast(ast))
            
            unknown = sorted(all_species_ids - known_species_ids)
            if unknown:
                raise ValueError(
                    f"Transition '{qt.getId()}' references unknown species: {', '.join(unknown)}"
                )

            # Create inputs for every species the rules reference
            for sid in sorted(all_species_ids):
                inp = qt.createInput()
                inp.setQualitativeSpecies(sid)
                if not inp.isSetMetaId():
                    inp.setMetaId(next_metaid())
                inp.setTransitionEffect(_qual_enum("QUAL_TRANSITION_EFFECT_NONE", 0))

            # Collect all rules for this transition to add as notes
            rules_list = []
            for t in target_transitions:
                level = t.level if t.level is not None else 1
                rules_list.append(f"Level {level}: {t.rule}")
            
            # Create function terms for each level
            for t in target_transitions:
                level = int(t.level) if t.level is not None else 1
                
                # Check if this transition is a constant
                is_const, const_level = is_constant_rule(t.rule)
                
                if is_const:
                    # For constant rules in multi-level models, still create a functionTerm
                    # but use <true/> or <false/> in MathML
                    ft = qt.createFunctionTerm()
                    ft.setResultLevel(level)
                    if const_level == 0:
                        mathml = "<math xmlns=\"http://www.w3.org/1998/Math/MathML\"><false/></math>"
                    else:
                        mathml = "<math xmlns=\"http://www.w3.org/1998/Math/MathML\"><true/></math>"
                    _set_mathml(ft, mathml)
                else:
                    # Normal rule - parse and convert to MathML
                    ft = qt.createFunctionTerm()
                    ft.setResultLevel(level)
                    
                    # Resolve rule names to IDs if use_name=True
                    rule = _resolve_rule_names_to_ids(t.rule, model.species) if use_name else t.rule
                    # Parse rule to MathML
                    ast = parse_expr(rule, known_species_ids)
                    mathml_content = ast_to_mathml(ast)
                    mathml = f"<math xmlns=\"http://www.w3.org/1998/Math/MathML\">{mathml_content}</math>"
                    _set_mathml(ft, mathml)
            
            # Add rules as notes to the transition
            if rules_list:
                _append_notes(qt, rules_list)
        
        # Notes and annotations from the first transition
        if first_transition.notes:
            _append_notes_concat(qt, first_transition.notes)
        if transitions_anno and first_transition.annotations:
            _add_annotations(qt, first_transition.annotations, use_model=False, print_messages=print_messages)

    # Interactions (optional): add to corresponding transition inputs
    # Always set signs from Interactions sheet, but only add annotations/notes if interactions_anno=True
    if model.interactions:
        for inter in model.interactions:
            # Resolve target and source names to IDs if use_name=True
            target_id = _resolve_name_to_id(inter.target, model.species) if use_name else inter.target
            source_id = _resolve_name_to_id(inter.source, model.species) if use_name else inter.source
            
            # Find transition whose output species equals interaction target
            for i in range(qual_model.getNumTransitions()):
                tr = qual_model.getTransition(i)
                out_species = None
                if tr.getNumOutputs() > 0:
                    out_species = tr.getOutput(0).getQualitativeSpecies()
                if out_species == target_id:
                    # Find matching input by species
                    found_input = None
                    try:
                        for j in range(tr.getNumInputs()):
                            candidate = tr.getInput(j)
                            if candidate.getQualitativeSpecies() == source_id:
                                found_input = candidate
                                break
                    except Exception:
                        found_input = None
                    if found_input is None:
                        if print_messages:
                            print(f"No input found for {source_id} in {tr.getId()}, creating one.")
                        found_input = tr.createInput()
                        found_input.setQualitativeSpecies(source_id)
                        if not found_input.isSetMetaId():
                            found_input.setMetaId(next_metaid())
                        found_input.setTransitionEffect(_qual_enum("QUAL_TRANSITION_EFFECT_NONE", 0))
                    # Always set sign from Interactions sheet
                    if inter.sign:
                        normalized_sign = (inter.sign or "").strip().lower()
                        try:
                            if normalized_sign == "positive":
                                found_input.setSign(_qual_enum("QUAL_SIGN_POSITIVE", 0))
                            elif normalized_sign == "negative":
                                found_input.setSign(_qual_enum("QUAL_SIGN_NEGATIVE", 1))
                            elif normalized_sign == "dual":
                                found_input.setSign(_qual_enum("QUAL_SIGN_DUAL", 2))
                            elif normalized_sign == "unknown":
                                found_input.setSign(_qual_enum("QUAL_SIGN_UNKNOWN", 3))
                            else:
                                _append_notes(found_input, [f"Sign: {inter.sign}"])
                        except Exception:
                            if print_messages:
                                print(f"Invalid sign: {inter.sign} for {inter.source} in {tr.getId()}, adding to notes.")
                            _append_notes(found_input, [f"Sign: {inter.sign}"])
                    # Only add annotations and notes if interactions_anno=True
                    if interactions_anno:
                        if inter.annotations:
                            _add_annotations(found_input, inter.annotations, use_model=False, print_messages=print_messages)
                        if inter.notes:
                            _append_notes(found_input, inter.notes)
                    break

    sbml_string = doc.toSBML()
    
    # Add XML declaration with encoding if not present
    if not sbml_string.startswith('<?xml'):
        sbml_string = '<?xml version="1.0" encoding="UTF-8"?>\n' + sbml_string
    
    # Clean up libsbml document to release memory
    del doc
    gc.collect()
    
    return sbml_string, warnings_list


def _set_mathml(ft: libsbml.QualFunctionTerm, mathml: str) -> None:
    astnode = libsbml.readMathMLFromString(mathml)
    if astnode is None:
        raise ValueError("Invalid MathML for function term")
    ft.setMath(astnode)


def _append_notes(node: libsbml.SBase, lines: List[str]) -> None:
    """Append notes to an SBML node
    
    For single notes or notes with embedded newlines, write directly.
    For multiple separate notes, wrap each with separator tags to preserve them through round-trips.
    """
    if not lines:
        return
    
    paragraphs = []
    
    if len(lines) == 1:
        # Single note - write directly without separators
        paragraphs.append(f"<p>{_xml_escape(lines[0])}</p>")
    else:
        # Multiple notes - wrap each with separator tags for round-trip preservation
        for idx, note in enumerate(lines, 1):
            wrapped = f"&lt;notes{idx}&gt;\n{_xml_escape(note)}\n&lt;/notes{idx}&gt;"
            paragraphs.append(f"<p>{wrapped}</p>")
    
    xhtml = "<body xmlns=\"http://www.w3.org/1999/xhtml\">" + "".join(paragraphs) + "</body>"
    node.setNotes(xhtml)


def _append_notes_concat(node: libsbml.SBase, lines: List[str]) -> None:
    """Append notes to existing notes instead of overwriting them"""
    existing_notes = ""
    if node.isSetNotes():
        existing_notes = node.getNotesString()
    
    new_notes = "\n".join([f"<p>{_xml_escape(l)}</p>" for l in lines])
    
    if existing_notes:
        # Extract the body content from existing notes
        if "<body" in existing_notes and "</body>" in existing_notes:
            start = existing_notes.find("<body")
            start = existing_notes.find(">", start) + 1
            end = existing_notes.find("</body>")
            if start > 0 and end > start:
                body_content = existing_notes[start:end]
                combined_content = body_content + new_notes
            else:
                combined_content = new_notes
        else:
            combined_content = existing_notes + new_notes
    else:
        combined_content = new_notes
    
    xhtml = f"<body xmlns=\"http://www.w3.org/1999/xhtml\">{combined_content}</body>"
    node.setNotes(xhtml)


def _xml_escape(s: str) -> str:
    # XML escaping to avoid parsing errors
    xml_escape_map = {
        "&": "&amp;",
        "<": "&lt;", 
        ">": "&gt;",
        "\"": "&quot;",
        "'": "&apos;"
    }
    for k, v in xml_escape_map.items():
        s = s.replace(k, v)
    return s


def _add_model_annotations(m: libsbml.Model, im: QualModel, print_messages: bool = True) -> None:
    # Publications / sources / derivedFrom etc. as CVTerms on model
    for url in im.model.source_urls:
        uri = _to_identifiers_url(url)
        _add_cvterm(m, True, getattr(libsbml, "BQM_IS", 0), uri)
    for url in im.model.described_by:
        uri = _to_identifiers_url(url)
        _add_cvterm(m, True, getattr(libsbml, "BQM_IS_DESCRIBED_BY", 0), uri)
    for url in im.model.derived_from:
        uri = _to_identifiers_url(url)
        _add_cvterm(m, True, getattr(libsbml, "BQM_IS_DERIVED_FROM", 0), uri)
    for proc in im.model.biological_processes:
        uri = _to_identifiers_url(proc)
        _add_cvterm(m, False, getattr(libsbml, "BQB_IS_VERSION_OF", 0), uri)
    for tax in im.model.taxons:
        uri = _to_identifiers_url(tax)
        _add_cvterm(m, False, getattr(libsbml, "BQB_HAS_TAXON", 0), uri)
    
    # Add other annotations (from notes or unknown qualifiers)
    if im.model.other_annotations:
        model_qualifiers = set(spec.RELATIONS_BQMODEL)
        for qualifier, identifier in im.model.other_annotations:
            use_model = qualifier in model_qualifiers
            _add_annotations(m, [(qualifier, identifier)], use_model, print_messages=print_messages)
    
    # TODO: hasProperty for MAMO terms based on species max_level
    # Model history: creators, contributors, created/modified using dc terms
    _add_model_history(m, im)


def _add_model_history(m: libsbml.Model, im: QualModel) -> None:
    try:
        history = libsbml.ModelHistory()
    except Exception:
        return
    
    # Creators
    has_creators = False
    for p in im.model.creators:
        c = libsbml.ModelCreator()
        if p.family_name:
            c.setFamilyName(p.family_name)
        if p.given_name:
            c.setGivenName(p.given_name)
        if p.email:
            c.setEmail(p.email)
        if p.organization:
            c.setOrganization(p.organization)
        history.addCreator(c)
        has_creators = True
    
    # If no creators, add a placeholder to enable model history
    # (libsbml requires at least one creator with both family and given names)
    if not has_creators:
        c = libsbml.ModelCreator()
        c.setFamilyName("Unknown")
        c.setGivenName("User")
        history.addCreator(c)
    
    # Contributors (not available in libsbml 5.20.4; fall back to addCreator)
    for p in im.model.contributors:
        c = libsbml.ModelCreator()
        if p.family_name:
            c.setFamilyName(p.family_name)
        if p.given_name:
            c.setGivenName(p.given_name)
        if p.email:
            c.setEmail(p.email)
        if p.organization:
            c.setOrganization(p.organization)
        if hasattr(history, "addContributor"):
            history.addContributor(c)
        else:
            import warnings as _w
            _w.warn(
                "This libsbml version does not support addContributor; "
                "contributor will be written as creator and read back as creator on round-trip."
            )
            history.addCreator(c)
    # Dates
    # Use current time if created_iso is None
    created_iso = im.model.created_iso
    if not created_iso:
        created_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Parse created date and create Date object with components
    # (libsbml's setDateAsString doesn't work reliably)
    created_dt = _to_iso8601(created_iso)
    if created_dt:
        try:
            d = libsbml.Date(
                created_dt.year,
                created_dt.month,
                created_dt.day,
                created_dt.hour,
                created_dt.minute,
                created_dt.second,
                1, 0, 0  # sign=1 (positive offset), hours offset=0, minutes offset=0
            )
            history.setCreatedDate(d)
        except Exception:
            pass
    
    # Parse modified date and create Date object with components
    if im.model.modified_iso:
        modified_dt = _to_iso8601(im.model.modified_iso)
        if modified_dt:
            try:
                d = libsbml.Date(
                    modified_dt.year,
                    modified_dt.month,
                    modified_dt.day,
                    modified_dt.hour,
                    modified_dt.minute,
                    modified_dt.second,
                    1, 0, 0
                )
                history.setModifiedDate(d)
            except Exception:
                pass
    
    m.setModelHistory(history)


def _add_annotations(node: libsbml.SBase, pairs: List[Tuple[str, str]], use_model: bool, print_messages: bool = True) -> None:
    """Add annotations to a node.
    
    Args:
        node: The SBML node to add annotations to
        pairs: List of (qualifier, identifier) tuples
        use_model: True for model qualifiers, False for biological qualifiers
    """
    from . import spec
    
    # For each (relation, identifiers_str) create one CVTerm with multiple resources if comma-separated
    for rel, ident in pairs:
        # Check if the qualifier is valid and print warning if not
        is_valid = False
        if use_model:
            # Check against model qualifiers
            valid_model_qualifiers = ["is", "isDerivedFrom", "isDescribedBy", "isInstanceOf", "hasInstance"]
            is_valid = rel in valid_model_qualifiers
        else:
            # Check against biological qualifiers (from spec.RELATIONS_BQBIOL)
            is_valid = rel in spec.RELATIONS_BQBIOL
        
        predicate = _relation_to_predicate(rel, use_model)
        
        if not is_valid and print_messages:
            converted_to = "bqmodel:is" if use_model else "bqbiol:is"
            print(f"Warning: Qualifier '{rel}' is not a valid {'model' if use_model else 'biological'} qualifier. Converting '{rel}' -> '{converted_to}'.")
        cv = libsbml.CVTerm(libsbml.MODEL_QUALIFIER if use_model else libsbml.BIOLOGICAL_QUALIFIER)
        cv.setQualifierType(libsbml.MODEL_QUALIFIER if use_model else libsbml.BIOLOGICAL_QUALIFIER)
        if use_model:
            cv.setModelQualifierType(predicate)
        else:
            cv.setBiologicalQualifierType(predicate)
        # split identifiers by comma into multiple resources within the same bag
        for token in [t.strip() for t in str(ident).split(',') if str(t).strip()]:
            uri = _to_identifiers_url(token)
            cv.addResource(uri)
        node.addCVTerm(cv)


def _relation_to_predicate(rel: str, use_model: bool) -> int:
    r = (rel or "").strip()
    if use_model:
        bqm = {
            "is": getattr(libsbml, "BQM_IS", 0),
            "isDerivedFrom": getattr(libsbml, "BQM_IS_DERIVED_FROM", 0),
            "isDescribedBy": getattr(libsbml, "BQM_IS_DESCRIBED_BY", 0),
            "isInstanceOf": getattr(libsbml, "BQM_IS_INSTANCE_OF", 0),
            "hasInstance": getattr(libsbml, "BQM_HAS_INSTANCE", 0),
        }
        return bqm.get(r, getattr(libsbml, "BQM_IS", 0))
    bqb = {
        "is": getattr(libsbml, "BQB_IS", 0),
        "hasVersion": getattr(libsbml, "BQB_HAS_VERSION", 0),
        "isVersionOf": getattr(libsbml, "BQB_IS_VERSION_OF", 0),
        "isDescribedBy": getattr(libsbml, "BQB_IS_DESCRIBED_BY", 0),
        "hasPart": getattr(libsbml, "BQB_HAS_PART", 0),
        "isPartOf": getattr(libsbml, "BQB_IS_PART_OF", 0),
        "hasProperty": getattr(libsbml, "BQB_HAS_PROPERTY", 0),
        "isPropertyOf": getattr(libsbml, "BQB_IS_PROPERTY_OF", 0),
        "encodes": getattr(libsbml, "BQB_ENCODES", 0),
        "isEncodedBy": getattr(libsbml, "BQB_IS_ENCODED_BY", 0),
        "isHomologTo": getattr(libsbml, "BQB_IS_HOMOLOG_TO", 0),
        "occursIn": getattr(libsbml, "BQB_OCCURS_IN", 0),
        "hasTaxon": getattr(libsbml, "BQB_HAS_TAXON", 0),
    }
    return bqb.get(r, getattr(libsbml, "BQB_IS", 0))


def _add_cvterm(node: libsbml.SBase, is_model: bool, predicate: int, uri: str) -> None:
    if is_model:
        cv = libsbml.CVTerm(libsbml.MODEL_QUALIFIER)
        cv.setQualifierType(libsbml.MODEL_QUALIFIER)
        cv.setModelQualifierType(predicate)
    else:
        cv = libsbml.CVTerm(libsbml.BIOLOGICAL_QUALIFIER)
        cv.setQualifierType(libsbml.BIOLOGICAL_QUALIFIER)
        cv.setBiologicalQualifierType(predicate)
    cv.addResource(uri)
    node.addCVTerm(cv)


def _to_identifiers_url(identifier: str) -> str:
    """Convert compact identifier or URL to identifiers.org URL
    
    Handles:
    - Direct URLs (http://, https://, ftp://) - kept as-is
    - URN format (urn:miriam:...) - kept as-is for compatibility
    - Compact IDs with colon (ncbigene:7132) -> https://identifiers.org/ncbigene:7132
    - Compact IDs with slash (ncbigene/7132) -> https://identifiers.org/ncbigene:7132
    - DOI format (doi:10.xxx) -> https://identifiers.org/doi:10.xxx
    - Plain strings -> https://identifiers.org/{string}
    """
    return to_identifiers_url(identifier)


def _collect_ids_from_ast(ast) -> List[str]:
    """Collect species IDs from AST, excluding numeric constants"""
    kind = ast[0]
    if kind == 'id':
        name = ast[1]
        # Skip numeric constants (e.g., "1", "0")
        if name.isdigit():
            return []
        return [name]
    if kind in ('eq', 'le', 'ge', 'gt', 'lt', 'neq'):
        return [ast[1]]  # Return the species name from threshold nodes
    if kind == 'not_species':
        return [ast[1]]  # Return the species name from negated species nodes
    if kind == 'not':
        return _collect_ids_from_ast(ast[1])
    if kind in ('and', 'or', 'xor'):
        return list(dict.fromkeys(_collect_ids_from_ast(ast[1]) + _collect_ids_from_ast(ast[2])))
    return []


def _qual_enum(name: str, default_value: int) -> int:
    # Gracefully resolve enums across libsbml versions
    value = getattr(libsbml, name, None)
    if isinstance(value, int):
        return value
    return default_value


def _to_iso8601(value: str | None):
    """Parse an ISO8601 date string and return a datetime object
    
    Returns:
        datetime object in UTC, or None if parsing fails
    """
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    # Try python-dateutil if available for robust parsing
    dt = None
    try:
        from dateutil import parser as dateutil_parser  # type: ignore
        dt = dateutil_parser.parse(s)
    except Exception:
        dt = None
    if dt is None:
        # Handle common cases
        # Replace trailing Z to be compatible with fromisoformat
        try:
            s2 = s
            if s.endswith("Z") and "+" not in s and "-" in s[10:]:
                # keep Z; fromisoformat does not like Z
                s2 = s.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s2)
        except Exception:
            dt = None
    if dt is None:
        # Try a set of common fallback formats (dates with/without time)
        fmts = [
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%m/%d/%Y",
            "%Y/%m/%d",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%d/%m/%Y %H:%M:%S",
            "%m/%d/%Y %H:%M",
            "%m/%d/%Y %H:%M:%S",
        ]
        for fmt in fmts:
            try:
                dt = datetime.strptime(s, fmt)
                break
            except Exception:
                continue
    if dt is None:
        return None
    # Normalize to UTC and return datetime object
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.replace(microsecond=0)
    except Exception:
        return None
