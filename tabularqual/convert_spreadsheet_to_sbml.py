from __future__ import annotations

from pathlib import Path
from .spreadsheet_reader import read_spreadsheet_to_model, detect_csv_input, read_csv_to_model
from .sbml_writer import write_sbml
from .tools import validate_sbml_file


def _get_version_info() -> str:
    """Get version information for TabularQual and libSBML"""
    try:
        from . import spec
        tabularqual_version = spec.VERSION
    except Exception:
        tabularqual_version = "unknown"
    
    try:
        import libsbml
        libsbml_version = libsbml.getLibSBMLDottedVersion()
    except Exception:
        libsbml_version = "unknown"
    
    return f"Created by TabularQual version {tabularqual_version} with libSBML version {libsbml_version}"

def convert_spreadsheet_to_sbml(input_path: str, output_sbml: str, *, interactions_anno: bool = True, transitions_anno: bool = True, print_messages: bool = True, validate: bool = True, use_name: bool = False) -> dict:
    """Convert spreadsheet (XLSX or CSV) to SBML and return statistics and warnings.
    
    Args:
        input_path: Path to input file. Can be:
            - An XLSX file path
            - A CSV file path (will look for sibling CSV files)
            - A directory containing CSV files
            - A prefix for CSV files (e.g., 'Example' for Example_Species.csv, etc.)
        output_sbml: Path to output SBML file
        interactions_anno: Whether to include interaction annotations
        transitions_anno: Whether to include transition annotations
        print_messages: Whether to print validation messages to console (set False for app use)
        validate: Whether to validate SBML annotations using sbmlutils (default True)
    
    Returns:
        dict: Statistics including 'species', 'transitions', 'interactions' counts, and 'warnings' list
    """
    input_p = Path(input_path)
    
    # Check if input is XLSX
    if input_p.is_file() and input_p.suffix.lower() in ('.xlsx', '.xls'):
        im, validation_warnings = read_spreadsheet_to_model(input_path, use_name=use_name)
    else:
        # Try CSV detection
        is_csv, csv_files, csv_warnings = detect_csv_input(input_path)
        
        if is_csv:
            # Print CSV detection warnings
            if print_messages:
                for warning in csv_warnings:
                    print(f"Warning: {warning}")
            
            # Check for required files
            if 'Species' not in csv_files or 'Transitions' not in csv_files:
                missing = []
                if 'Species' not in csv_files:
                    missing.append('Species')
                if 'Transitions' not in csv_files:
                    missing.append('Transitions')
                raise ValueError(f"Missing required CSV file(s): {', '.join(missing)}")
            
            im, validation_warnings = read_csv_to_model(csv_files, use_name=use_name)
            # Prepend CSV detection warnings
            validation_warnings = csv_warnings + validation_warnings
        else:
            # Fallback to XLSX (will raise error if file doesn't exist)
            im, validation_warnings = read_spreadsheet_to_model(input_path, use_name=use_name)
    
    # Print warnings to console
    if print_messages:
        for warning in validation_warnings:
            if warning.startswith("Found ") or warning.startswith("No "):
                print(warning)  # Info messages
            else:
                print(f"Warning: {warning}")  # Actual warnings
    
    # Collect stats
    sbml_string, writer_warnings = write_sbml(im, interactions_anno=interactions_anno, transitions_anno=transitions_anno, use_name=use_name, print_messages=print_messages)
    
    # Combine all warnings
    all_warnings = validation_warnings + writer_warnings
    
    stats = {
        'species': len(im.species),
        'transitions': len(im.transitions),
        'interactions': len(im.interactions),
        'warnings': all_warnings
    }
    
    # Insert version comment
    version_comment = f"<!-- {_get_version_info()} -->\n"
    lines = sbml_string.split('\n')
    lines.insert(1, version_comment)
    
    # Write the modified SBML to file
    with open(output_sbml, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    
    # Validate the output SBML annotations (if enabled)
    if validate:
        # For CLI (print_messages=True): limit to 10, for app (print_messages=False): get all
        max_errors = 10 if print_messages else None
        validation_result = validate_sbml_file(output_sbml, max_errors=max_errors, print_messages=print_messages)
    else:
        validation_result = {
            'warnings': [],
            'errors': [],
            'total_errors': 0,
            'validation_run': False,
        }
    
    # Add validation results to stats for app display
    stats['validation_errors'] = validation_result.get('errors', [])
    stats['total_validation_errors'] = validation_result.get('total_errors', 0)
    
    return stats
