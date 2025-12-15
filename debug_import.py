
import sys
import os

print("Python executable:", sys.executable)
print("CWD:", os.getcwd())

src_path = r"d:\VITRIFY\src"
print(f"Adding {src_path} to sys.path")
sys.path.append(src_path)

try:
    import igu_recovery
    print("Imported igu_recovery:", igu_recovery)
    from igu_recovery.utils import calculations
    print("Imported calculations:", calculations)
    print("SUCCESS")
except Exception as e:
    print("ERROR:", e)
    import traceback
    traceback.print_exc()
