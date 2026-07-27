import os
import json
import shutil
import asyncio
import tempfile
import zipfile
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from tabularqual.convert_spreadsheet_to_sbml import convert_spreadsheet_to_sbml
from tabularqual.convert_sbml_to_spreadsheet import (
    convert_sbml_to_spreadsheet,
    get_default_template_path,
)

app = FastAPI(title="TabularQual API")
lock = asyncio.Semaphore(1) # Ensure only one request at a time

def cleanup_files(file_paths: list[str]):
    """Background task to delete files after the response is sent."""
    for path in file_paths:
        if not path:
            continue
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        except FileNotFoundError:
            pass

@app.post("/to-sbml")
async def api_to_sbml(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...), # Parameter name must be 'files'
    inter_anno: bool = Form(True),
    trans_anno: bool = Form(True),
    validate_annotations: bool = Form(False, alias="validate"),
    use_name: bool = Form(False)
):
    async with lock:
        temp_dir = tempfile.mkdtemp(prefix="tabularqual_")

        try:
            uploaded_names = set()
            for file in files:
                safe_name = os.path.basename(file.filename or "")
                if not safe_name or safe_name in {".", ".."}:
                    raise ValueError("An uploaded file has an invalid filename")
                if safe_name in uploaded_names:
                    raise ValueError(f"Duplicate uploaded filename: {safe_name}")
                uploaded_names.add(safe_name)

                file_path = os.path.join(temp_dir, safe_name)
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
            
            # Logic to handle both single XLSX and CSV directory structure
            if len(files) == 1 and safe_name.lower().endswith((".xlsx", ".xls")):
                input_path = os.path.join(temp_dir, safe_name)
            else:
                input_path = temp_dir

            output_sbml = os.path.join(temp_dir, "model.sbml")
            
            stats = convert_spreadsheet_to_sbml(
                input_path, output_sbml, 
                interactions_anno=inter_anno, 
                transitions_anno=trans_anno,
                validate=validate_annotations,
                use_name=use_name,
                print_messages=False
            )
            
            background_tasks.add_task(cleanup_files, [temp_dir])
            
            return FileResponse(
                output_sbml, 
                filename="model.sbml",
                headers={
                    "X-Stats-Species": str(stats['species']),
                    "X-Stats-Transitions": str(stats['transitions']),
                    "X-Stats-Interactions": str(stats['interactions']),
                    "X-Warnings": json.dumps(stats['warnings']),
                    "X-Validation-Errors": json.dumps(stats.get('validation_errors', []))
                }
            )
        except Exception as e:
            cleanup_files([temp_dir])
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/to-table")
async def api_to_table(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    colon_format: bool = Form(False),
    use_name: bool = Form(False),
    validate_annotations: bool = Form(False, alias="validate"),
    output_csv: bool = Form(False)
):
    async with lock:
        temp_dir = tempfile.mkdtemp(prefix="tabularqual_")
        temp_in = os.path.join(temp_dir, "input.sbml")
        temp_out = os.path.join(
            temp_dir, "model" if output_csv else "model.xlsx"
        )
        
        try:
            with open(temp_in, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            rule_format = "colon" if colon_format else "operators"
            
            # Use the packaged default template for XLSX output.
            template_path = get_default_template_path() if not output_csv else None

            stats = convert_sbml_to_spreadsheet(
                temp_in, temp_out, 
                template_path=template_path,
                rule_format=rule_format, 
                output_csv=output_csv,
                validate=validate_annotations,
                use_name=use_name,
                print_messages=False
            )
            # If CSV, zip the multiple created files
            if output_csv:
                zip_path = f"{temp_out}_archive.zip"
                with zipfile.ZipFile(zip_path, 'w') as zipf:
                    for f in stats['created_files']:
                        original_name = os.path.basename(f)
                        # Remove the temporary CSV prefix from the download name.
                        clean_name = (
                            original_name.split("_", 1)[1]
                            if "_" in original_name
                            else original_name
                        )
                        zipf.write(f, clean_name)

            background_tasks.add_task(cleanup_files, [temp_dir])
            
            return FileResponse(
                zip_path if output_csv else stats['created_files'][0],
                filename="model.xlsx" if not output_csv else "model_csv.zip",
                headers={
                    "X-Stats-Species": str(stats['species']),
                    "X-Stats-Transitions": str(stats['transitions']),
                    "X-Stats-Interactions": str(stats['interactions']),
                    "X-Warnings": json.dumps(stats['warnings']), 
                    "X-Validation-Errors": json.dumps(stats['validation_errors'])
                }
            )

        except Exception as e:
            cleanup_files([temp_dir])
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    return {"message": "TabularQual API is running. Go to /docs for the interactive UI."}
