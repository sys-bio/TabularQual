import requests
import os

BASE_URL = "https://tabularqual.onrender.com"
# BASE_URL = "http://127.0.0.1:8000"

def test_to_sbml(input_path):
    print(f"\n>>> Starting [to-sbml] conversion for: {input_path}")
    url = f"{BASE_URL}/to-sbml"
    
    files_to_send = []
    if os.path.isdir(input_path):
        # directory for csv files
        for filename in os.listdir(input_path):
            if filename.endswith(('.csv', '.xlsx')):
                fpath = os.path.join(input_path, filename)
                files_to_send.append(('files', (filename, open(fpath, 'rb'))))
    else:
        # single xlsx file
        files_to_send.append(('files', (os.path.basename(input_path), open(input_path, 'rb'))))

    # API options, same as CLI
    data = {'validate': 'false', 'use_name': 'false', 'inter_anno': 'true', 'trans_anno': 'true'}
    
    try:
        response = requests.post(url, files=files_to_send, data=data)
        if response.status_code == 200:
            output = "demo_output.sbml"
            with open(output, "wb") as f:
                f.write(response.content)
                print(f"Successfully saved to: {output}")
                print(f"Species Count: {response.headers.get('X-Stats-Species')}")
                print(f"Transitions Count: {response.headers.get('X-Stats-Transitions')}")
                print(f"Interactions Count: {response.headers.get('X-Stats-Interactions')}")
                print(f"Warnings: {response.headers.get('X-Warnings')}")
                # print(f"Validation Errors: {response.headers.get('X-Validation-Errors')}")
            return output
        else:
            print(f"Error {response.status_code}: {response.text}")
    finally:
        for _, file_tuple in files_to_send:
            file_tuple[1].close()

def test_to_table(sbml_file, as_csv=False):
    mode = "CSV (ZIP)" if as_csv else "XLSX"
    print(f"\n>>> Starting [to-table] conversion ({mode}) for: {sbml_file}")
    
    url = f"{BASE_URL}/to-table"
    
    files = {'file': open(sbml_file, 'rb')}
    data = {
        'validate': 'false',
        'output_csv': 'true' if as_csv else 'false',
        'colon_format': 'false',
        'use_name': 'false'
    }

    response = requests.post(url, files=files, data=data)

    if response.status_code == 200:
        ext = ".zip" if as_csv else ".xlsx"
        output_name = f"demo_output{ext}"
        
        with open(output_name, "wb") as f:
            f.write(response.content)
        
        print(f"Successfully saved to: {output_name}")
        print(f"Species Count: {response.headers.get('X-Stats-Species')}")
        print(f"Transitions Count: {response.headers.get('X-Stats-Transitions')}")
        print(f"Interactions Count: {response.headers.get('X-Stats-Interactions')}")
        print(f"Warnings: {response.headers.get('X-Warnings')}")
        # print(f"Validation Errors: {response.headers.get('X-Validation-Errors')}")
    else:
        print(f"Error {response.status_code}: {response.text}")

if __name__ == "__main__":
    test_xlsx = "examples/ToyExample.xlsx"
    test_csv_folder = "examples/ToyExample_csv/"

    if os.path.exists(test_xlsx) and os.path.exists(test_csv_folder):
        # 1. Spreadsheet to SBML
        sbml_out = test_to_sbml(test_xlsx)

        # 2. CSV to SBML
        sbml_out = test_to_sbml(test_csv_folder)
        
        if sbml_out:
            # 3. SBML to XLSX
            test_to_table(sbml_out, as_csv=False)
            
            # 4. SBML to CSV (Zipped)
            test_to_table(sbml_out, as_csv=True)
    else:
        print(f"Please ensure {test_xlsx} exists to run the demo.")
