import re

with open('../05模型/PROSAIL_D_MATLAB_2017/dataSpec_PDB.m', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

pattern = r'(\d+)\s+([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)\s+([\d.E+-]+)'

matches = re.findall(pattern, content)

print(f"Found {len(matches)} data rows")
print("Generating Python data...")

data_lines = []
for m in matches:
    wl = int(m[0])
    values = [float(x) for x in m[1:]]
    data_lines.append(f"    {wl:4d}: [{', '.join([f'{v:.4e}' for v in values])}],")

print("const_spectral_data = {")
for line in data_lines[:10]:
    print(line)
print("    ...")
for line in data_lines[-5:]:
    print(line)
print("}")

numpy_array_str = "np.array(["
for m in matches:
    values = [f"{float(x):.6e}" for x in m[1:]]
    numpy_array_str += f"\n    [{', '.join(values)}],"
numpy_array_str += "\n])"

print("\n\nnp.savez_compressed('spectral_data.npz', data=" + numpy_array_str + ")")

output_file = "spectral_data_full.py"
with open(output_file, 'w') as f:
    f.write("import numpy as np\n\n")
    f.write("def get_spectral_data():\n")
    f.write("    return np.array([\n")
    for m in matches:
        values = [f"{float(x):.6e}" for x in m[1:]]
        f.write(f"        [{', '.join(values)}],\n")
    f.write("    ], dtype=np.float64)\n")
    
print(f"Written to {output_file}")