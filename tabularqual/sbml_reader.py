from __future__ import annotations

from typing import Any, List, Tuple, Dict
import html
import libsbml
from xml.etree import ElementTree as ET
import os
import gc
import warnings
from datetime import datetime, timezone

from .types import QualModel, ModelInfo, Species, Transition, InteractionEvidence, Person


def read_sbml(sbml_path: str) -> QualModel:
    """Read an SBML-qual file and convert it to QualModel"""
    doc = libsbml.readSBMLFromFile(sbml_path)
    
    try:
        errors = []
        has_layout_errors = False
        for i in range(doc.getNumErrors()):
            err = doc.getError(i)
            if err.getSeverity() >= libsbml.LIBSBML_SEV_ERROR:
                if err.getPackage() == 'layout':
                    has_layout_errors = True
                else:
                    errors.append(str(err.getMessage()))
        if has_layout_errors:
            warnings.warn(
                "Layout information found in SBML file is not supported and will be ignored. "
                "Layout will not be preserved in the output."
            )

        model = doc.getModel()
        if model is None:
            raise ValueError(f"SBML parsing errors: {'; '.join(errors)}" if errors else "No model found in SBML file")

        qual_model = model.getPlugin("qual")
        if qual_model is None:
            raise ValueError(f"SBML parsing errors: {'; '.join(errors)}" if errors else "No qual plugin found in model")

        if errors:
            warnings.warn(
                f"SBML file has {len(errors)} structural error(s) but model content was read. "
                f"Some information may be incomplete. First error: {errors[0]}"
            )
        
        # Read model info
        model_info = _read_model_info(model, sbml_path)
        
        # Read species
        species_dict = _read_species(qual_model)
        
        # Read transitions
        transitions, interactions = _read_transitions(qual_model, species_dict)
        
        result = QualModel(
            model=model_info,
            species=species_dict,
            transitions=transitions,
            interactions=interactions
        )
        
        return result
    finally:
        # delete the libsbml document
        del doc
        gc.collect()


def _read_model_info(model: libsbml.Model, sbml_path: str) -> ModelInfo:
    """Extract model-level information"""
    if model.isSetId():
        model_id = model.getId()
    else:
        # Use filename without extension if no id provided
        filename = os.path.basename(sbml_path)
        model_id = os.path.splitext(filename)[0]
    
    name = model.getName() if model.isSetName() else None
    
    # Parse notes
    notes = []
    versions = []
    if model.isSetNotes():
        notes_str = model.getNotesString()
        # Extract notes
        extracted_notes = _extract_text_from_notes(notes_str)
        for note in extracted_notes:
            # Check for version information
            if note.startswith('Version:'):
                versions.append(note.replace('Version:', '').strip())
            else:
                notes.append(note)
    
    # Parse annotations
    source_urls = []
    described_by = []
    derived_from = []
    biological_processes = []
    taxons = []
    other_annotations = []
    created_iso = None
    modified_iso = None
    creators = []
    contributors = []
    
    if model.isSetAnnotation():
        anno_str = model.getAnnotationString()
        anno_dict = _parse_rdf_annotation(anno_str)
        
        source_urls = anno_dict.get('bqmodel:is', [])
        described_by = anno_dict.get('bqmodel:isDescribedBy', [])
        derived_from = anno_dict.get('bqmodel:isDerivedFrom', [])
        biological_processes = anno_dict.get('bqbiol:isVersionOf', [])
        taxons = anno_dict.get('bqbiol:hasTaxon', [])
        
        # Timestamps
        if 'dcterms:created' in anno_dict:
            created_iso = anno_dict['dcterms:created'][0]
        if 'dcterms:modified' in anno_dict:
            modified_iso = anno_dict['dcterms:modified'][0]
        
        # Creators and contributors
        if 'dcterms:creator' in anno_dict:
            creators = anno_dict['dcterms:creator']
        if 'dcterms:contributor' in anno_dict:
            contributors = anno_dict['dcterms:contributor']
        
        # Collect other qualifiers not handled above
        known_keys = {
            'bqmodel:is', 'bqmodel:isDescribedBy', 'bqmodel:isDerivedFrom',
            'bqbiol:isVersionOf', 'bqbiol:hasTaxon',
            'dcterms:created', 'dcterms:modified', 'dcterms:creator', 'dcterms:contributor'
        }
        for key, values in anno_dict.items():
            if key not in known_keys and (key.startswith('bqmodel:') or key.startswith('bqbiol:')):
                # Store as (qualifier_name, url) tuples
                qualifier_name = key.split(':', 1)[1] if ':' in key else key
                # Print warning for unknown qualifier
                warnings.warn(f"Model annotation: Found unknown/invalid qualifier '{qualifier_name}' in SBML file. This will be stored in Model Notes.")
                for url in values:
                    other_annotations.append((qualifier_name, url))
    
    # Set current time if Created field is empty
    if not created_iso:
        created_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    return ModelInfo(
        model_id=model_id,
        name=name,
        source_urls=source_urls,
        described_by=described_by,
        derived_from=derived_from,
        biological_processes=biological_processes,
        taxons=taxons,
        created_iso=created_iso,
        modified_iso=modified_iso,
        creators=creators,
        contributors=contributors,
        versions=versions,
        notes=notes,
        other_annotations=other_annotations
    )


def _read_species(qual_model) -> Dict[str, Species]:
    """Read all qualitative species"""
    species_dict = {}
    
    for i in range(qual_model.getNumQualitativeSpecies()):
        qs = qual_model.getQualitativeSpecies(i)
        species_id = qs.getId()
        name = qs.getName() if qs.isSetName() else None
        compartment = qs.getCompartment() if qs.isSetCompartment() else None
        constant = qs.getConstant() if qs.isSetConstant() else None
        initial_level = qs.getInitialLevel() if qs.isSetInitialLevel() else None
        max_level = qs.getMaxLevel() if qs.isSetMaxLevel() else None
        
        # Parse notes and extract type information
        notes = []
        species_type = None
        if qs.isSetNotes():
            notes_str = qs.getNotesString()
            all_notes = _extract_text_from_notes(notes_str)
            # Check for type information in notes
            for note in all_notes:
                if note.startswith("Type:"):
                    # Extract type value
                    type_value = note.replace("Type:", "").strip()
                    # Validate against allowed types
                    from . import spec
                    species_type = spec.normalize_type(type_value)
                else:
                    notes.append(note)
        
        # Parse annotations
        annotations = []
        if qs.isSetAnnotation():
            anno_str = qs.getAnnotationString()
            annotations = _parse_annotations_to_list(anno_str)
            # Check for unknown qualifiers and warn
            from . import spec
            for qualifier, identifier in annotations:
                if qualifier not in spec.RELATIONS_BQBIOL:
                    warnings.warn(f"Species '{species_id}': Found unknown/invalid qualifier '{qualifier}' in SBML file.")
        
        species_dict[species_id] = Species(
            species_id=species_id,
            name=name,
            compartment=compartment,
            constant=constant,
            initial_level=initial_level,
            max_level=max_level,
            type=species_type,
            annotations=annotations,
            notes=notes
        )
    
    return species_dict


def _read_transitions(qual_model, species_dict=None) -> Tuple[List[Transition], List[InteractionEvidence]]:
    """Read all transitions and extract interaction information"""
    transitions = []
    interactions = []
    
    for i in range(qual_model.getNumTransitions()):
        tr = qual_model.getTransition(i)
        transition_id = tr.getId() if tr.isSetId() else None
        name = tr.getName() if tr.isSetName() else None
        
        # Get target (output)
        outputs = []
        for j in range(tr.getNumOutputs()):
            out = tr.getOutput(j)
            outputs.append(out.getQualitativeSpecies())
        
        if not outputs:
            continue
        target = outputs[0]  # Should only have one output per transition
        
        # Get inputs and their signs
        inputs_with_signs = []
        input_thresholds = {}
        for j in range(tr.getNumInputs()):
            inp = tr.getInput(j)
            source = inp.getQualitativeSpecies()
            sign = inp.getSign() if inp.isSetSign() else None
            threshold = inp.getThresholdLevel() if inp.isSetThresholdLevel() else 1
            input_id = inp.getId() if inp.isSetId() else None
            if input_id:
                input_thresholds[input_id] = threshold
            
            # Convert libsbml sign enum to string
            sign_str = None
            if sign is not None:
                if sign == libsbml.INPUT_SIGN_POSITIVE:
                    sign_str = "positive"
                elif sign == libsbml.INPUT_SIGN_NEGATIVE:
                    sign_str = "negative"
                elif sign == libsbml.INPUT_SIGN_DUAL:
                    sign_str = "dual"
                elif sign == libsbml.INPUT_SIGN_UNKNOWN:
                    sign_str = "unknown"
            
            inputs_with_signs.append((source, sign_str, threshold))
            
            # Extract interaction-level annotations if present
            inter_notes = []
            inter_annotations = []
            if inp.isSetNotes():
                notes_str = inp.getNotesString()
                inter_notes = _extract_text_from_notes(notes_str)
            if inp.isSetAnnotation():
                anno_str = inp.getAnnotationString()
                inter_annotations = _parse_annotations_to_list(anno_str)
                # Check for unknown qualifiers and warn
                from . import spec
                for qualifier, identifier in inter_annotations:
                    if qualifier not in spec.RELATIONS_BQBIOL:
                        warnings.warn(f"Interaction (target='{target}', source='{source}'): Found unknown/invalid qualifier '{qualifier}' in SBML file.")
            
            if sign_str or inter_annotations or inter_notes:
                interactions.append(InteractionEvidence(
                    target=target,
                    source=source,
                    sign=sign_str,
                    annotations=inter_annotations,
                    notes=inter_notes
                ))
        
        # Parse transition notes (filter out "Level X:" lines)
        notes = []
        if tr.isSetNotes():
            notes_str = tr.getNotesString()
            notes = _extract_text_from_notes(notes_str, filter_level_prefix=True)
        
        # Parse transition annotations
        annotations = []
        if tr.isSetAnnotation():
            anno_str = tr.getAnnotationString()
            annotations = _parse_annotations_to_list(anno_str)
            # Check for unknown qualifiers and warn
            from . import spec
            for qualifier, identifier in annotations:
                if qualifier not in spec.RELATIONS_BQBIOL:
                    transition_name = transition_id if transition_id else f"target={target}"
                    warnings.warn(f"Transition '{transition_name}': Found unknown/invalid qualifier '{qualifier}' in SBML file.")
        
        # Get function terms and create separate transitions for each level
        # Detect constant rules: no function terms and default term exists
        # Note: We don't require getNumInputs() == 0 because some SBML encoders
        # might include inputs even for constant rules (inputs are irrelevant without functionTerms)
        is_constant_rule = False
        default_level = 0
        
        if tr.getNumFunctionTerms() == 0:
            # Get default term (might exist even if getNumFunctionTerms() returns 0)
            if hasattr(tr, 'getDefaultTerm'):
                dt = tr.getDefaultTerm()
                if dt and dt.isSetResultLevel():
                    default_level = dt.getResultLevel()
                    is_constant_rule = True
        
        # Collect all non-default function terms
        function_terms = []
        for j in range(tr.getNumFunctionTerms()):
            ft = tr.getFunctionTerm(j)
            if ft.isSetResultLevel() and ft.getResultLevel() > 0:  # Skip default term (level 0)
                level = ft.getResultLevel()
                rule = None
                if ft.isSetMath():
                    math_ast = ft.getMath()
                    rule = _mathml_to_rule(math_ast, inputs_with_signs, input_thresholds, species_dict)
                
                # If no rule found, create default
                if rule is None and inputs_with_signs:
                    rule = " & ".join([src for src, _, _ in inputs_with_signs])
                
                # Warn about blank or empty rules
                if not rule or rule.strip() == "" or rule.strip() == "()":
                    warnings.warn(f"Warning: Transition for target '{target}' has blank or empty rule. Setting to 1 (default level).")
                    rule = "1"

                function_terms.append((level, rule or ""))
        
        # If no function terms with rules, create one transition without level
        if not function_terms:
            rule = None
            level = None
            
            # Check if this is a constant rule
            if is_constant_rule:
                # Use FALSE for 0, numeric string for other levels (preserves multi-valued)
                if default_level == 0:
                    rule = "FALSE"
                elif default_level == 1:
                    rule = "TRUE"
                else:
                    rule = str(default_level)
            elif rule is None and inputs_with_signs:
                rule = " & ".join([src for src, _, _ in inputs_with_signs])
            
            # Warn about blank or empty rules (but not for constant rules)
            if not rule or (rule.strip() == "" or rule.strip() == "()"):
                warnings.warn(f"Warning: Transition for target '{target}' has blank or empty rule. Setting to FALSE.")
                rule = "FALSE"

            transitions.append(Transition(
                transition_id=transition_id,
                name=name,
                target=target,
                level=level,
                rule=rule or "",
                annotations=annotations,
                notes=notes
            ))
        else:
            # Create separate transition for each function term (level)
            for idx, (level, rule) in enumerate(function_terms):
                # Create transition ID with level suffix if multiple levels
                if len(function_terms) > 1:
                    tid = f"{transition_id}_{level}" if transition_id else None
                else:
                    tid = transition_id
                
                transitions.append(Transition(
                    transition_id=tid,
                    name=name,
                    target=target,
                    level=level,
                    rule=rule,
                    annotations=annotations,
                    notes=notes
                ))
    
    return transitions, interactions


def _mathml_to_rule(math_ast, inputs_with_signs, input_thresholds=None, species_dict=None) -> str:
    """Convert MathML AST to rule string.

    Per SBML-qual spec (section 5.1), <ci> references to Input id attributes
    are substituted with the corresponding thresholdLevel value. This enables
    Boolean simplification (e.g., x >= 1 -> x, x < 1 -> !x).
    Boolean simplifications for == 1 / != 1 are skipped for multi-valued species.
    """
    if input_thresholds is None:
        input_thresholds = {}

    def _is_multivalued(name: str) -> bool:
        if species_dict is None:
            return False
        sp = species_dict.get(name)
        return sp is not None and sp.max_level is not None and sp.max_level > 1
    
    def convert_ast_node(node) -> str:
        """Recursively convert AST node to expression string"""
        if node is None:
            return ""
        
        node_type = node.getType()
        
        # Logical operators
        # Parenthesisation is decided by child node TYPE, not by string inspection.
        # String-based checks like '" & " in c' are unreliable: a child that is
        # itself an OR expression may transitively contain '&' inside its already-
        # parenthesised AND sub-terms, causing spurious extra wrapping each round-trip.
        #
        # Helper functions are intentionally avoided here; nested closures add one
        # extra frame per level of recursion and can cause RecursionError on models
        # with many binary-nested OR terms.
        if node_type == libsbml.AST_LOGICAL_AND:
            # Wrap OR/XOR children (lower precedence than AND).
            parts = []
            for i in range(node.getNumChildren()):
                ch = node.getChild(i)
                s = convert_ast_node(ch)
                ct = ch.getType()
                parts.append(
                    f"({s})" if ct in (libsbml.AST_LOGICAL_OR, libsbml.AST_LOGICAL_XOR)
                    else s
                )
            return " & ".join(parts)

        elif node_type == libsbml.AST_LOGICAL_OR:
            # Wrap AND/XOR children for readability; never wrap OR children.
            parts = []
            for i in range(node.getNumChildren()):
                ch = node.getChild(i)
                s = convert_ast_node(ch)
                ct = ch.getType()
                parts.append(
                    f"({s})" if ct in (libsbml.AST_LOGICAL_AND, libsbml.AST_LOGICAL_XOR)
                    else s
                )
            return " | ".join(parts)

        elif node_type == libsbml.AST_LOGICAL_XOR:
            # Wrap OR and AND children for clarity.
            parts = []
            for i in range(node.getNumChildren()):
                ch = node.getChild(i)
                s = convert_ast_node(ch)
                ct = ch.getType()
                parts.append(
                    f"({s})" if ct in (libsbml.AST_LOGICAL_OR, libsbml.AST_LOGICAL_AND)
                    else s
                )
            return " ^ ".join(parts)
        
        elif node_type == libsbml.AST_LOGICAL_NOT:
            child = convert_ast_node(node.getChild(0))
            # Add parentheses if child is complex
            if " " in child:
                return f"!({child})"
            return f"!{child}"
        
        # Relational operators
        elif node_type == libsbml.AST_RELATIONAL_EQ:
            left = convert_ast_node(node.getChild(0))
            right = convert_ast_node(node.getChild(1))
            if right == "1" or right == "1.0":
                # For multi-valued species, eq(X, 1) != geq(X, 1); keep explicit
                if _is_multivalued(left):
                    return f"{left} == 1"
                return left
            elif right == "0" or right == "0.0":
                if " " in left:
                    return f"!({left})"
                return f"!{left}"
            return f"{left} == {right}"

        elif node_type == libsbml.AST_RELATIONAL_NEQ:
            left = convert_ast_node(node.getChild(0))
            right = convert_ast_node(node.getChild(1))
            if right == "0" or right == "0.0":
                return left
            if right == "1" or right == "1.0":
                # For multi-valued species, neq(X, 1) != lt(X, 1); keep explicit
                if _is_multivalued(left):
                    return f"{left} != 1"
                if " " in left:
                    return f"!({left})"
                return f"!{left}"
            return f"{left} != {right}"
        
        elif node_type == libsbml.AST_RELATIONAL_LT:
            left = convert_ast_node(node.getChild(0))
            right = convert_ast_node(node.getChild(1))
            if right == "1" or right == "1.0":
                if " " in left:
                    return f"!({left})"
                return f"!{left}"
            if right == "0" or right == "0.0":
                return "FALSE"
            return f"{left} < {right}"
        
        elif node_type == libsbml.AST_RELATIONAL_LEQ:
            left = convert_ast_node(node.getChild(0))
            right = convert_ast_node(node.getChild(1))
            if right == "0" or right == "0.0":
                if " " in left:
                    return f"!({left})"
                return f"!{left}"
            return f"{left} <= {right}"
        
        elif node_type == libsbml.AST_RELATIONAL_GT:
            left = convert_ast_node(node.getChild(0))
            right = convert_ast_node(node.getChild(1))
            if right == "0" or right == "0.0":
                return left
            return f"{left} > {right}"
        
        elif node_type == libsbml.AST_RELATIONAL_GEQ:
            left = convert_ast_node(node.getChild(0))
            right = convert_ast_node(node.getChild(1))
            # Handle "species >= 1" -> just "species"
            if right == "1" or right == "1.0":
                return left
            return f"{left} >= {right}"
        
        # Boolean constants
        elif node_type == libsbml.AST_CONSTANT_TRUE:
            return "TRUE"
        
        elif node_type == libsbml.AST_CONSTANT_FALSE:
            return "FALSE"
        
        # Variables and constants
        elif node_type == libsbml.AST_NAME:
            name = node.getName()
            if name and name.strip() in input_thresholds:
                return str(input_thresholds[name.strip()])
            return name
        
        elif node_type == libsbml.AST_INTEGER:
            return str(node.getInteger())
        
        elif node_type == libsbml.AST_REAL:
            val = node.getReal()
            if val == int(val):
                return str(int(val))
            return str(val)
        
        # Fallback
        else:
            return libsbml.formulaToL3String(node)
    
    result = convert_ast_node(math_ast)
    # Clean up empty results or "()" patterns
    if result and result.strip() in ["", "()", "(  )"]:
        return ""
    return result


def _parse_rdf_annotation(anno_str: str) -> Dict[str, List[Any]]:
    """Parse RDF annotation string into a dictionary"""
    result: Dict[str, List[Any]] = {}
    
    try:
        # Parse XML
        root = ET.fromstring(anno_str)
        
        # Define namespaces
        ns = {
            'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
            'dc': 'http://purl.org/dc/elements/1.1/',
            'dcterms': 'http://purl.org/dc/terms/',
            'vCard': 'http://www.w3.org/2001/vcard-rdf/3.0#',
            'bqbiol': 'http://biomodels.net/biology-qualifiers/',
            'bqmodel': 'http://biomodels.net/model-qualifiers/'
        }
        
        # Find all RDF descriptions
        for desc in root.findall('.//rdf:Description', ns):
            # Parse timestamp elements
            for elem_name in ['dcterms:created', 'dcterms:modified']:
                elem = desc.find(f'.//{elem_name}', ns)
                if elem is not None:
                    dtf = elem.find('.//dcterms:W3CDTF', ns)
                    if dtf is not None and dtf.text:
                        result[elem_name] = [dtf.text]
            
            # Parse creator/contributor (support both dc: and dcterms: namespaces)
            for elem_name in ['dcterms:creator', 'dcterms:contributor', 'dc:creator', 'dc:contributor']:
                creators_elem = desc.find(f'.//{elem_name}', ns)
                if creators_elem is not None:
                    persons = []
                    for li in creators_elem.findall('.//rdf:li', ns):
                        person = Person()
                        n_elem = li.find('.//vCard:N', ns)
                        if n_elem is not None:
                            family = n_elem.find('.//vCard:Family', ns)
                            given = n_elem.find('.//vCard:Given', ns)
                            if family is not None and family.text:
                                person.family_name = family.text
                            if given is not None and given.text:
                                person.given_name = given.text
                        
                        org_elem = li.find('.//vCard:ORG', ns)
                        if org_elem is not None:
                            orgname = org_elem.find('.//vCard:Orgname', ns)
                            if orgname is not None and orgname.text:
                                person.organization = orgname.text
                        
                        email_elem = li.find('.//vCard:EMAIL', ns)
                        if email_elem is not None and email_elem.text:
                            person.email = email_elem.text
                        
                        persons.append(person)
                    # Normalize dc: to dcterms: for consistent downstream access
                    normalized_key = elem_name.replace('dc:', 'dcterms:')
                    if normalized_key in result:
                        result[normalized_key].extend(persons)
                    else:
                        result[normalized_key] = persons
            
            # Parse resource references (URLs)
            for prefix in ['bqmodel', 'bqbiol']:
                for elem in desc.findall(f'.//{prefix}:*', ns):
                    qual_name = elem.tag.split('}')[-1]
                    key = f"{prefix}:{qual_name}"
                    urls = []
                    for li in elem.findall('.//rdf:li', ns):
                        resource = li.get('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource')
                        if resource:
                            urls.append(resource)
                    if urls:
                        if key in result:
                            result[key].extend(urls)
                        else:
                            result[key] = urls
    
    except Exception:
        pass
    
    return result


def _parse_annotations_to_list(anno_str: str) -> List[Tuple[str, str]]:
    """Parse RDF annotation into list of (qualifier, identifier) tuples"""
    annotations = []
    
    try:
        # libsbml may return annotation strings without namespace declarations
        # Add them if missing to enable proper XML parsing
        if '<rdf:RDF>' in anno_str or '<rdf:RDF ' in anno_str:
            # Check if namespace declarations are missing
            if 'xmlns:rdf=' not in anno_str:
                anno_str = anno_str.replace(
                    '<rdf:RDF',
                    '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
                    'xmlns:bqbiol="http://biomodels.net/biology-qualifiers/" '
                    'xmlns:bqmodel="http://biomodels.net/model-qualifiers/" '
                    'xmlns:dcterms="http://purl.org/dc/terms/"'
                )
        
        root = ET.fromstring(anno_str)
        ns = {
            'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
            'bqbiol': 'http://biomodels.net/biology-qualifiers/',
            'bqmodel': 'http://biomodels.net/model-qualifiers/'
        }
        
        for desc in root.findall('.//rdf:Description', ns):
            for prefix in ['bqmodel', 'bqbiol']:
                for elem in desc.findall(f'.//{prefix}:*', ns):
                    qual_name = elem.tag.split('}')[-1]
                    for li in elem.findall('.//rdf:li', ns):
                        resource = li.get('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}resource')
                        if resource:
                            annotations.append((qual_name, resource))
    
    except Exception:
        pass
    
    return annotations


def _extract_text_from_notes(notes_str: str, filter_level_prefix: bool = False) -> List[str]:
    """Extract text content from XHTML notes
    
    Args:
        notes_str: The XHTML notes string
        filter_level_prefix: If True, filter out lines starting with "Level X:"
    
    Returns:
        List of note strings, where each <p> tag becomes a separate note
    """
    notes = []
    
    try:
        # Remove namespace declarations for easier parsing
        notes_str = notes_str.replace(' xmlns="http://www.w3.org/1999/xhtml"', '')
        root = ET.fromstring(notes_str)
        
        def _add_text(text):
            """Add extracted text to notes, handling separator tags and level filtering."""
            if not text:
                return
            import re
            pattern = r'<notes(\d+)>\s*(.*?)\s*</notes\1>'
            matches = re.findall(pattern, text, re.DOTALL)
            if matches:
                for _, content in matches:
                    content = content.strip()
                    if content:
                        if filter_level_prefix and content.startswith('Level ') and ':' in content:
                            continue
                        notes.append(content)
            else:
                if filter_level_prefix and text.startswith('Level ') and ':' in text:
                    return
                notes.append(text)
        
        # Collect text from <p> and leaf <div> elements (divs with no child <p>/<div>)
        seen_texts = set()
        for elem in root.iter():
            tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
            if tag == 'p':
                text = ''.join(elem.itertext()).strip()
                if text and text not in seen_texts:
                    seen_texts.add(text)
                    _add_text(text)
            elif tag == 'div':
                has_block_children = any(
                    (child.tag.split('}')[-1] if '}' in child.tag else child.tag) in ('p', 'div')
                    for child in elem
                )
                if not has_block_children:
                    text = ''.join(elem.itertext()).strip()
                    if text and text not in seen_texts:
                        seen_texts.add(text)
                        _add_text(text)
    
    except Exception:
        # Fallback: just extract text between tags
        import re
        text = re.sub('<[^>]+>', '', notes_str)
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        for line in lines:
            if filter_level_prefix and line.startswith('Level ') and ':' in line:
                continue
            if line:
                notes.append(line)
    
    return [html.unescape(note) for note in notes]
