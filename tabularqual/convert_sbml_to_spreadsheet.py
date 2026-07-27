from __future__ import annotations

import warnings
from pathlib import Path

from .sbml_reader import read_sbml
from .spreadsheet_writer import write_spreadsheet, write_csv, check_xlsx_rule_overflow, _EXCEL_MAX_CELL_LEN
from .tools import validate_sbml_file


def get_default_template_path() -> str | None:
    """Find the packaged default spreadsheet template.
    
    Returns:
        Path to template.xlsx if it exists, otherwise None.
    """
    template = Path(__file__).parent / "data" / "template.xlsx"
    return str(template) if template.exists() else None


def convert_sbml_to_spreadsheet(sbml_path: str, output_path: str, template_path: str | None = None, rule_format: str = "operators", output_csv: bool = False, print_messages: bool = True, validate: bool = True, use_name: bool = False) -> dict:
    """
    Convert an SBML-qual file to SpreadSBML spreadsheet format (XLSX or CSV).
    
    Args:
        sbml_path: Path to input SBML file
        output_path: Path to output file. For CSV output, this is the prefix for output files.
        template_path: Optional path to template.xlsx for README and Appendix sheets (XLSX only)
        rule_format: Format for transition rules - "operators" (default, uses >=, <=, etc.) or "colon" (uses : notation)
        output_csv: If True, output as CSV files instead of XLSX
        print_messages: Whether to print messages to console (set False for app use)
        validate: Whether to validate SBML annotations using sbmlutils (default True)
    
    Returns:
        dict: Statistics including 'species', 'transitions', 'interactions' counts,
              'warnings' list, 'created_files' list, and validation results
    """
    # Suppress openpyxl warnings
    warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')
    
    # Capture warnings during SBML reading
    all_warnings = []
    
    # Validate input SBML annotations first (if enabled)
    if validate:
        # For CLI (print_messages=True): limit to 10, for app (print_messages=False): get all
        max_errors = 10 if print_messages else None
        validation_result = validate_sbml_file(sbml_path, max_errors=max_errors, print_messages=print_messages)
    else:
        validation_result = {
            'warnings': [],
            'errors': [],
            'total_errors': 0,
            'validation_run': False,
        }
    
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        
        # Read SBML
        model = read_sbml(sbml_path)
        
        # Capture any warnings
        for warning in w:
            warning_msg = str(warning.message)
            all_warnings.append(warning_msg)
            if print_messages:
                print(warning_msg)
    
    # Add info messages
    species_msg = f"Found {len(model.species)} species"
    transitions_msg = f"Found {len(model.transitions)} transitions"
    interactions_msg = f"Found {len(model.interactions)} interactions"
    
    if print_messages:
        print(species_msg)
        print(transitions_msg)
        print(interactions_msg)
    
    all_warnings.append(species_msg)
    all_warnings.append(transitions_msg)
    all_warnings.append(interactions_msg)
    
    # Write output
    if not output_csv:
        overflows = check_xlsx_rule_overflow(model)
        if overflows:
            # Fall back to CSV: rules too long for Excel cells
            output_csv = True
            names = ", ".join(f"'{tid}'" for tid, _, _ in overflows)
            msg = (
                f"Transition rule(s) {names} exceed Excel's cell limit "
                f"({_EXCEL_MAX_CELL_LEN} chars). Saving as CSV files instead to preserve full rules."
            )
            all_warnings.append(msg)
            if print_messages:
                print(f"Warning: {msg}")

    if output_csv:
        # Derive CSV prefix from output_path (strip .xlsx/.xls extension if present)
        from pathlib import Path as _Path
        csv_prefix = str(_Path(output_path).with_suffix('')) if _Path(output_path).suffix.lower() in ('.xlsx', '.xls', '.xlsm') else output_path
        created_files = write_csv(model, csv_prefix, rule_format, use_name=use_name)
    else:
        actual_path, _ = write_spreadsheet(model, output_path, template_path, rule_format, use_name=use_name)
        created_files = [actual_path]
    
    return {
        'species': len(model.species),
        'transitions': len(model.transitions),
        'interactions': len(model.interactions),
        'warnings': all_warnings,
        'created_files': created_files,
        'validation_errors': validation_result.get('errors', []),
        'total_validation_errors': validation_result.get('total_errors', 0),
    }
