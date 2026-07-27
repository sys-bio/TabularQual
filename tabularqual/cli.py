from __future__ import annotations

import click
from pathlib import Path
from .convert_spreadsheet_to_sbml import convert_spreadsheet_to_sbml
from .convert_sbml_to_spreadsheet import convert_sbml_to_spreadsheet, get_default_template_path


@click.group()
def main():
    pass


def _resolve_annotation_flags(inter_anno: bool, trans_anno: bool) -> tuple[bool, bool]:
    # If neither or both are provided, use both
    if (not inter_anno and not trans_anno) or (inter_anno and trans_anno):
        return True, True
    # Only one provided: select that one exclusively
    if inter_anno:
        return True, False
    return False, True


def _check_input_exists(input_path: str) -> bool:
    """Check if input exists - supports files, directories, and CSV prefixes."""
    p = Path(input_path)
    if p.exists():
        return True
    
    # Check if it's a prefix for CSV files
    # Handle both relative ("test") and absolute ("/path/to/test") paths
    if p.is_absolute():
        base_dir = p.parent
    else:
        base_dir = Path.cwd() / p.parent if str(p.parent) != '.' else Path.cwd()
    
    prefix = p.name.lower()
    
    if not base_dir.exists():
        return False
    
    for f in base_dir.iterdir():
        if f.is_file() and f.suffix.lower() == '.csv':
            if f.stem.lower().startswith(prefix + '_'):
                return True
    
    return False


def _get_output_name(input_path: str, new_extension: str) -> str:
    """Generate output filename based on input, replacing or adding extension."""
    p = Path(input_path)
    # For CSV prefix input (no extension), use the name directly
    if p.suffix.lower() in ('.xlsx', '.xls', '.sbml', '.xml', '.csv'):
        return str(p.with_suffix(new_extension))
    else:
        # It's a prefix or directory name
        return str(p) + new_extension


@click.command(name="to-sbml")
@click.argument("input_path", type=click.Path())
@click.argument("output_sbml", type=click.Path(), required=False)
@click.option("--inter-anno", is_flag=True, default=False, help="Use interaction annotations only (unless --trans-anno also set)")
@click.option("--trans-anno", is_flag=True, default=False, help="Use transition annotations only (unless --inter-anno also set)")
@click.option("--no-validate", is_flag=True, default=False, help="Skip SBML annotation validation")
@click.option("--use-name", "use_name", is_flag=True, default=False, help="Use Species Name instead of ID in rules and interactions. Default: use ID.")
def to_sbml_entry(input_path: str, output_sbml: str | None, inter_anno: bool, trans_anno: bool, no_validate: bool, use_name: bool):
    """Convert spreadsheet (XLSX or CSV) to SBML.
    
    INPUT_PATH: XLSX file, CSV file, directory with CSVs, or CSV prefix
    
    OUTPUT_SBML: Output SBML file (optional, defaults to input name with .sbml extension)
    """
    # Validate input exists
    if not _check_input_exists(input_path):
        raise click.ClickException(f"Input not found: {input_path}")
    
    # Default output name if not provided
    if output_sbml is None:
        output_sbml = _get_output_name(input_path, '.sbml')
    
    interactions_anno, transitions_anno = _resolve_annotation_flags(inter_anno, trans_anno)
    try:
        convert_spreadsheet_to_sbml(
            input_path,
            output_sbml,
            interactions_anno=interactions_anno,
            transitions_anno=transitions_anno,
            validate=not no_validate,
            use_name=use_name,
        )
    except ValueError as e:
        raise click.ClickException(str(e))
    click.echo(f"Wrote SBML to {output_sbml}")


@click.command(name="to-table")
@click.argument("input_sbml", type=click.Path(exists=True))
@click.argument("output_path", type=click.Path(), required=False)
@click.option("--template", "template_xlsx", type=click.Path(exists=True, dir_okay=False), help="Template file for README and Appendix sheets (XLSX only)")
@click.option("--colon-format", "colon_format", is_flag=True, default=False, help="Use colon notation for transition rules (A:2 means A>=2). Default uses operators (>=, <, etc.)")
@click.option("--csv", "output_csv", is_flag=True, default=False, help="Output as CSV files instead of XLSX")
@click.option("--no-validate", is_flag=True, default=False, help="Skip SBML annotation validation")
@click.option("--use-name", "use_name", is_flag=True, default=False, help="Use Species Name instead of ID in rules and interactions. Default: use ID.")
def to_table_entry(input_sbml: str, output_path: str | None, template_xlsx: str | None = None, colon_format: bool = False, output_csv: bool = False, no_validate: bool = False, use_name: bool = False):
    """Convert SBML to spreadsheet (XLSX or CSV).
    
    INPUT_SBML: Input SBML file
    
    OUTPUT_PATH: Output file/prefix (optional, defaults to input name). For CSV output, this is the prefix for files.
    """
    # Default output name if not provided
    if output_path is None:
        if output_csv:
            # For CSV, use the input stem as prefix
            output_path = Path(input_sbml).stem
        else:
            output_path = _get_output_name(input_sbml, '.xlsx')
    
    # Auto-detect template if not provided (only for XLSX output)
    if template_xlsx is None and not output_csv:
        template_xlsx = get_default_template_path()
    
    rule_format = "colon" if colon_format else "operators"
    result = convert_sbml_to_spreadsheet(input_sbml, output_path, template_xlsx, rule_format, output_csv, validate=not no_validate, use_name=use_name)
    
    created_files = result['created_files']
    if output_csv:
        click.echo("Wrote CSV files:")
        for f in created_files:
            click.echo(f"  - {f}")
    else:
        click.echo(f"Wrote spreadsheet to {created_files[0]}")


# Add the commands to the main group
main.add_command(to_sbml_entry)
main.add_command(to_table_entry)


if __name__ == "__main__":
    main()
