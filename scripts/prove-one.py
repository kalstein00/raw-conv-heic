"""Developer evidence runner, not a supported product CLI."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import platform
import sys

from rawhdr import convert_raw, verify_heic

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
try:
    report_path = args.output.with_suffix('.report.json')
    if not args.output.exists() and (report_path.exists() or args.output.with_suffix('.sdr.png').exists()):
        raise FileExistsError('Evidence report/preview already exists; choose another output name')
    result = convert_raw(args.source, args.output)
    report = asdict(result)
    report['output'] = str(result.output)
    report['environment'] = {'platform': platform.platform(), 'python': platform.python_version()}
    # Preview is a separate developer evidence artifact, never an HDR proof.
    if result.status == 'success':
        verify_heic(result.output, preview_path=result.output.with_suffix(".sdr.png"))
        with report_path.open('x', encoding='utf-8') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))
except Exception as error:
    print(json.dumps({'status': 'failed', 'error_type': type(error).__name__, 'error': str(error)}), file=sys.stderr)
    raise SystemExit(1)
