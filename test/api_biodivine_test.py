import requests
import os
import time
import csv

# This is a manual remote benchmark script, not a pytest test module.
__test__ = False

# Configuration
BASE_URL = "https://tabularqual.onrender.com"
SBML_DIR = '/Users/luna/Desktop/CRBM/AMAS_proj/Models/BioDivine_260125/'
SHEET_DIR = '/Users/luna/Desktop/CRBM/AMAS_proj/Models/BioDivine_260125/spreadsheets/'
RESULTS_CSV = "api_biodivine_results.csv"

def log_result(test_type, filename, duration, status, error=""):
    """Helper to append test results to CSV."""
    file_exists = os.path.isfile(RESULTS_CSV)
    with open(RESULTS_CSV, 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['Test Type', 'File', 'Duration (s)', 'Status', 'Error/Warnings'])
        writer.writerow([test_type, filename, round(duration, 4), status, error])

def test_directory(directory, endpoint, is_to_sbml=True):
    """Iterates through a directory and hits the specified API endpoint."""
    print(f"\n>>> Starting Batch Test for: {endpoint}")
    
    if not os.path.exists(directory):
        print(f"Directory {directory} not found. Skipping.")
        return

    for filename in os.listdir(directory):
        # Filter for relevant files based on the endpoint
        if is_to_sbml and not filename.endswith(('.xlsx', '.xls', '.csv')):
            continue
        if not is_to_sbml and not filename.endswith(('.sbml', '.xml')):
            continue

        file_path = os.path.join(directory, filename)
        print(f"Testing {filename}...", end=" ", flush=True)
        
        start_time = time.time()
        try:
            # Handle directory vs file for to-sbml (CSV sets)
            files_to_send = []
            if os.path.isdir(file_path):
                for sub_f in os.listdir(file_path):
                    files_to_send.append(('files', (sub_f, open(os.path.join(file_path, sub_f), 'rb'))))
            else:
                files_to_send.append(('files' if is_to_sbml else 'file', (filename, open(file_path, 'rb'))))

            # Send request with standard flags
            response = requests.post(
                f"{BASE_URL}{endpoint}",
                files=files_to_send,
                data={'use_name': 'true', 'validate': 'false'},
                timeout=300 # 5 minute timeout for large models
            )
            
            duration = time.time() - start_time
            
            if response.status_code == 200:
                # Capture warnings from headers
                warnings = response.headers.get('X-Warnings', '[]')
                log_result(endpoint, filename, duration, "Success", warnings)
                print(f"Done ({round(duration, 2)}s)")
            else:
                log_result(endpoint, filename, duration, f"Error {response.status_code}", response.text)
                print(f"Failed ({response.status_code})")

        except Exception as e:
            duration = time.time() - start_time
            log_result(endpoint, filename, duration, "Crash/Exception", str(e))
            print("Crashed")
        
        # Short pause to let server RAM recover
        time.sleep(2)

if __name__ == "__main__":
    # 1. Test SBML -> Spreadsheet (to-table)
    test_directory(SBML_DIR, "/to-table", is_to_sbml=False)
    
    # 2. Test Spreadsheet -> SBML (to-sbml)
    test_directory(SHEET_DIR, "/to-sbml", is_to_sbml=True)

    print(f"\nAll tests complete. Results saved to {RESULTS_CSV}")
