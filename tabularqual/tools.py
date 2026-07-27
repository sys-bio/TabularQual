RDF_TAG_ITEM = ['rdf:RDF',
                'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"',
                'xmlns:bqbiol="http://biomodels.net/biology-qualifiers/"']

RDF_TAG = ' '.join(RDF_TAG_ITEM)

import re
from typing import TypedDict

from .identifiers import to_identifiers_url


# SId validation regex pattern (SBML Level 3 Version 2 specification)
# Must start with a letter (A–Z, a–z) or underscore (_)
# May contain only letters, digits (0–9), and underscores
# Uses plain ASCII characters (no Unicode)
SID_PATTERN = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def is_valid_sid(identifier: str) -> bool:
    """
    Check if identifier conforms to SBML SId definition.
    
    An SId has the following properties:
    - Must start with a letter (A–Z, a–z) or underscore (_)
    - May contain only letters, digits (0–9), and underscores
    - Case-sensitive, equality determined by exact string matching
    - Does not allow spaces, slashes, or other special characters
    - Uses plain ASCII characters (no Unicode)
    
    Args:
        identifier: The identifier string to validate
        
    Returns:
        True if valid SId, False otherwise
    """
    if not identifier or not isinstance(identifier, str):
        return False
    return bool(SID_PATTERN.match(identifier))


def clean_sid(identifier: str) -> tuple[str, list[str]]:
    """
    Clean an identifier to conform to SBML SId definition.
    
    Transformation rules:
    1. Replace spaces, slashes, dashes, and other special characters with underscores
    2. If starts with a digit, prepend underscore
    3. Remove any remaining non-alphanumeric, non-underscore characters
    4. Collapse multiple consecutive underscores to single underscore
    5. Remove leading/trailing underscores (except if needed for digit start)
    
    Args:
        identifier: The original identifier string
        
    Returns:
        tuple: (cleaned_id, list of transformation messages)
    """
    if not identifier or not isinstance(identifier, str):
        return "", ["Empty or invalid identifier"]
    
    original = identifier.strip()
    if not original:
        return "", ["Empty identifier after stripping whitespace"]
    
    messages = []
    cleaned = original
    
    # Track what changes we make
    changes = []
    
    # Step 1: Replace common special characters with underscores
    special_chars_pattern = re.compile(r'[\s/\-\\:;.,+*=<>()[\]{}|&^%$#@!~`\'"?]')
    if special_chars_pattern.search(cleaned):
        cleaned = special_chars_pattern.sub('_', cleaned)
        changes.append("replaced special characters with underscores")
    
    # Step 2: Remove any remaining non-ASCII or non-alphanumeric/underscore characters
    non_ascii_pattern = re.compile(r'[^A-Za-z0-9_]')
    if non_ascii_pattern.search(cleaned):
        cleaned = non_ascii_pattern.sub('', cleaned)
        changes.append("removed non-ASCII characters")
    
    # Step 3: Collapse multiple consecutive underscores
    if '__' in cleaned:
        cleaned = re.sub(r'_+', '_', cleaned)
        changes.append("collapsed multiple underscores")
    
    # Step 4: Handle leading digit by prepending underscore
    if cleaned and cleaned[0].isdigit():
        cleaned = '_' + cleaned
        changes.append("prepended underscore (ID cannot start with digit)")
    
    # Step 5: Remove leading/trailing underscores (but keep one leading if needed for digit start)
    if cleaned:
        # Trim trailing underscores
        cleaned = cleaned.rstrip('_')
        # Trim leading underscores, but keep one if first char after underscores is a digit
        leading_stripped = cleaned.lstrip('_')
        if leading_stripped and leading_stripped[0].isdigit():
            cleaned = '_' + leading_stripped
        else:
            cleaned = leading_stripped
    
    # If empty after cleaning, generate a fallback
    if not cleaned:
        cleaned = "unknown_id"
        changes.append("generated fallback ID (original was invalid)")
    
    # Final validation check
    if not is_valid_sid(cleaned):
        # This shouldn't happen with our cleaning logic, but just in case
        cleaned = "unknown_id"
        changes.append("generated fallback ID (cleaning failed)")
    
    if changes:
        messages.append(f"'{original}' → '{cleaned}' ({'; '.join(changes)})")
    
    return cleaned, messages


def validate_and_clean_sid(identifier: str, field_name: str, context: str = "") -> tuple[str, list[str]]:
    """
    Validate an SId and clean it if invalid, returning warnings.
    
    Args:
        identifier: The identifier to validate
        field_name: Name of the field (e.g., "Species_ID", "Transitions_ID", "Compartment")
        context: Additional context for error messages (e.g., "row 5")
        
    Returns:
        tuple: (final_id, list of warning messages)
    """
    warnings: list[str] = []
    
    if not identifier:
        return identifier, warnings
    
    if is_valid_sid(identifier):
        return identifier, warnings
    
    # Invalid SId - clean it
    cleaned_id, clean_messages = clean_sid(identifier)
    
    context_str = f" ({context})" if context else ""
    for msg in clean_messages:
        warnings.append(f"{field_name}{context_str}: Invalid SId cleaned: {msg}")
    
    return cleaned_id, warnings

def getIndent(num_indents=0):
  """
  Parameters
  ----------
  num_indents: int
    Time of indentation
  
  Returns
  -------
  :str
  """
  return '  ' * (num_indents)
  
def insertList(insert_to,
                insert_from,
                start_loc=None):
  """
  Insert a list to another list.

  Parameters
  ----------
  insert_to:list
      List where new list is inserted to

  inser_from: list
      A list where items will be inserted from

  start_loc: int
      If not given, insert_from will be 
      added in the middle of insert_to
  """
  if start_loc is None:
    start_loc = int(len(insert_to)/2)
  indents = getIndent(start_loc)
  insert_from_indented = [indents+val for val in insert_from]
  return insert_to[:start_loc] + \
          insert_from_indented + \
          insert_to[start_loc:]

def createAnnotationItem(knowledge_source,
                          identifier):
  """
  Create a one-line annotation,
  e.g., <rdf:li rdf:resource="http://identifiers.org/chebi/CHEBI:15414"/>

  Parameters
  ----------
  knowledge_source: str

  identifier: str

  Returns
  -------
  str
  """
  annotation_items = ['identifiers.org',
                      knowledge_source,
                      identifier]
  res = '<rdf:li rdf:resource="http://' + \
        '/'.join(annotation_items)  +\
        '"/>'
  return res

def createTag(tag_str):
  """
  Create a tag based on the given string
  
  Parameters
  ---------
  str: inp_str

  Returns
  -------
  list-str
  """
  head_str = tag_str
  tail_str = tag_str.split(' ')[0]
  res_tag = ['<'+head_str+'>', '</'+tail_str+'>']
  return res_tag

def createAnnotationContainer(items):
  """
  Create an empty annotation container
  that will hold the annotation blocks

  Parameters
  ----------
  items: str-list

  Returns
  -------
  list-str
  """
  container: list[str] = []
  for one_item in items:
    one_t = createTag(one_item)
    container = insertList(insert_from=one_t,
                                insert_to=container)
  return container

def createAnnotationString(qualifier,
                        knowledge_source,
                        candidates,
                        meta_id):
  """
  Create a string of annotations,
  using a list of strings.
  (of candidates)
  Can replace an entire annotation. 

  Parameters
  ----------
  qualifier: str
      Qualifier to be used for annotations.
      E.g., 'bqbiol:isDescribedBy'

  knowledge_source: str
      Knowledge source of the annotation.
      E.g., 'uniprot'

  candidates: list-str
      e.g., ['CHEBI:12345', 'CHEBI:98765']

  meta_id: str
      Meta ID of the element to be included in the annotation. 

  Returns
  -------
  str
  """
      
  # First, construct an empty container
  container_items = ['annotation', 
                      RDF_TAG,
                      'rdf:Description rdf:about="#' + str(meta_id) + '"',
                      qualifier,
                      'rdf:Bag']
  empty_container = createAnnotationContainer(container_items)
  # Next, create annotation lines
  items_from = []
  for one_cand in candidates:
    if one_cand != '':
      items_from.append(createAnnotationItem(knowledge_source,one_cand))

  result = insertList(insert_to=empty_container,
                              insert_from=items_from)
  return ('\n').join(result)

def createAnnotationStringFromDict(all_annotations, meta_id):
    """
    Create a complete RDF annotation string from a dictionary of annotations.
    
    Parameters:
    -----------
    all_annotations: dict
        A nested dictionary with the structure:
        {
            'relation1': {
                'resource1': ['id1', 'id2'],
                'resource2': ['id3', 'id4']
            },
            'relation2': {
                'resource3': ['id5', 'id6']
            }
        }
    meta_id: str
        MetaID of the species
        
    Returns:
    --------
    str
        Complete annotation string
    """
    # Start RDF annotation
    annotation_string = (
        '<annotation>\n'
        '  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
        'xmlns:bqbiol="http://biomodels.net/biology-qualifiers/">\n'
        f'    <rdf:Description rdf:about="#{meta_id}">\n'
    )
    
    # Add each relation and its resources/identifiers
    for relation, resources in all_annotations.items():
        for resource, identifiers in resources.items():
            # Skip if no valid identifiers
            if not identifiers:
                continue
                
            # Remove duplicates while preserving order
            unique_identifiers = []
            for id in identifiers:
                if id and id not in unique_identifiers:
                    unique_identifiers.append(id)
            
            # Skip if no valid identifiers after removing duplicates
            if not unique_identifiers:
                continue
            
            # Add this relation with all its identifiers
            annotation_string += f'      <bqbiol:{relation}>\n'
            annotation_string += '        <rdf:Bag>\n'
            
            for identifier in unique_identifiers:
                annotation_string += f'          <rdf:li rdf:resource="http://identifiers.org/{resource}/{identifier}"/>\n'
            
            annotation_string += '        </rdf:Bag>\n'
            annotation_string += f'      </bqbiol:{relation}>\n'
    
    # Close the tags
    annotation_string += '    </rdf:Description>\n'
    annotation_string += '  </rdf:RDF>\n'
    annotation_string += '</annotation>'
    
    return annotation_string

def validate_identifier(identifier: str) -> dict:
    """
    Validate and classify a spreadsheet identifier.
    
    Args:
        identifier: The identifier string from the spreadsheet
        
    Returns:
        Dictionary with classification and processed URI
    """
    if not identifier or not isinstance(identifier, str):
        return {
            'is_valid': False,
            'type': 'invalid',
            'uri': identifier,
            'error': 'Empty or non-string identifier'
        }
    
    s = identifier.strip()
    if not s:
        return {
            'is_valid': False,
            'type': 'invalid',
            'uri': identifier,
            'error': 'Empty identifier after stripping'
        }
    
    # Check if it's already a URL/URI
    if s.startswith(("http://", "https://", "ftp://")):
        return {
            'is_valid': True,
            'type': 'url',
            'uri': to_identifiers_url(s),
            'original': identifier
        }
    
    # Check if it's a URN
    if s.startswith("urn:"):
        return {
            'is_valid': True,
            'type': 'urn',
            'uri': to_identifiers_url(s),
            'original': identifier
        }
    
    # Check if it's a DOI
    if s.startswith("doi:"):
        return {
            'is_valid': True,
            'type': 'doi',
            'uri': to_identifiers_url(s),
            'original': identifier
        }
    
    # Check if it's a compact identifier (prefix:accession pattern)
    if ":" in s and not s.startswith(":"):
        # For compact identifiers, we expect at least one colon
        # The first colon separates prefix from accession, but prefix may contain colons
        
        # Split on first colon only
        first_colon_pos = s.find(":")
        if first_colon_pos > 0:  # prefix exists and is not empty
            prefix = s[:first_colon_pos]
            accession = s[first_colon_pos + 1:]
            
            # Basic validation: prefix should not be empty, accession should not be empty
            if prefix and accession:
                return {
                    'is_valid': True,
                    'type': 'compact_identifier',
                    'uri': to_identifiers_url(s),
                    'original': identifier,
                    'prefix': prefix,
                    'accession': accession
                }
            else:
                return {
                    'is_valid': False,
                    'type': 'malformed_compact',
                    'uri': identifier,
                    'error': 'Empty prefix or accession in compact identifier'
                }
        else:
            return {
                'is_valid': False,
                'type': 'malformed_compact',
                'uri': identifier,
                'error': 'Invalid compact identifier format'
            }
    
    # For identifiers without colons, assume they might be compact identifiers
    # but this is less certain
    return {
        'is_valid': True,
        'type': 'assumed_compact',
        'uri': to_identifiers_url(s),
        'original': identifier,
        'warning': 'No colon found, assuming compact identifier'
    }


class ValidationResult(TypedDict):
    warnings: list[str]
    errors: list[str]
    total_errors: int
    validation_run: bool


def validate_sbml_file(
    sbml_path: str,
    max_errors: int | None = 10,
    print_messages: bool = True,
) -> ValidationResult:
    """Validate SBML annotations using sbmlutils.
    
    Args:
        sbml_path: Path to SBML file (will be converted to absolute path)
        max_errors: Maximum number of error messages to return (first N). Use None for all.
        print_messages: Whether to print our own formatted validation summary to console
    
    Returns:
        dict with keys:
            - 'warnings': list of warning messages
            - 'errors': list of error messages (up to max_errors, or all if max_errors is None)
            - 'total_errors': total number of errors found
            - 'validation_run': bool indicating if validation was run
    """
    from pathlib import Path
    import sys
    import os
    
    result: ValidationResult = {
        'warnings': [],
        'errors': [],
        'total_errors': 0,
        'validation_run': False
    }
    
    try:
        from sbmlutils.metadata.validator import validate_sbml_annotations
        
        # Convert to absolute path to avoid libsbml path issues
        abs_path = Path(sbml_path).resolve()
        if not abs_path.exists():
            result['errors'].append(f"File not found: {sbml_path}")
            return result
        
        # Always suppress sbmlutils output - may be too long
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        try:
            with open(os.devnull, 'w') as devnull:
                sys.stdout = devnull
                sys.stderr = devnull
                validation_df = validate_sbml_annotations(abs_path)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
        
        result['validation_run'] = True
        
        if validation_df is None or (hasattr(validation_df, 'empty') and validation_df.empty):
            # Empty DataFrame means all annotations are valid
            if print_messages:
                print("Annotation validation: All annotations valid.")
            return result
        
        result['total_errors'] = len(validation_df)
        
        # Collect error messages (limited or all)
        rows_to_process = validation_df if max_errors is None else validation_df.head(max_errors)
        for idx, row in rows_to_process.iterrows():
            element_id = row.get('id', 'unknown')
            resource = row.get('resource', 'unknown')
            msg = f"Invalid annotation for '{element_id}': {resource}"
            result['errors'].append(msg)
        
        # Print our own formatted output
        if print_messages:
            print(f"\nAnnotation validation: {result['total_errors']} invalid annotation(s) found.")
            for i, error in enumerate(result['errors']):
                print(f"  {i+1}. {error}")
            if max_errors is not None and result['total_errors'] > max_errors:
                print(f"  ... and {result['total_errors'] - max_errors} more error(s)")
        
    except ImportError:
        msg = "sbmlutils.metadata.validator not available - annotation validation skipped"
        result['warnings'].append(msg)
        if print_messages:
            print(f"Note: {msg}")
    except Exception as e:
        result['errors'].append(f"Validation error: {str(e)}")
    
    return result
