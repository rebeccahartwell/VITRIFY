import sys
import os

# Add the current directory to sys.path so we can import the package
# if this script is run from the src directory.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from igu_recovery.main import main

if __name__ == "__main__":
    main()
