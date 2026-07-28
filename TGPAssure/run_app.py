import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

print('Starting TGPAssure Application...')

from main import main

sys.exit(main())
