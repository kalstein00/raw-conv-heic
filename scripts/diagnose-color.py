"""Local SDR symptom check against an accepted camera HIF, not a color fidelity certification."""
import argparse
import json
from pathlib import Path
import numpy as np
from PIL import Image
import pillow_heif

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('reference', type=Path)
parser.add_argument('candidate', type=Path)
args = parser.parse_args()

def pixels(path):
    if path.suffix.lower() in ('.heic', '.hif', '.heif'):
        image = pillow_heif.open_heif(path).to_pillow()
    else:
        image = Image.open(path).convert('RGB')
    image.thumbnail((1000, 1000))
    return np.asarray(image, dtype=np.float32) / 255

reference, candidate = pixels(args.reference), pixels(args.candidate)
if reference.shape != candidate.shape:
    raise ValueError('Oriented image sizes differ')
weights = np.array([.2126, .7152, .0722])
ref_luma, candidate_luma = reference @ weights, candidate @ weights
mask = (ref_luma > .15) & (ref_luma < .85)
ref_max, candidate_max = reference.max(2), candidate.max(2)
ref_sat = (ref_max - reference.min(2)) / np.maximum(ref_max, .001)
candidate_sat = (candidate_max - candidate.min(2)) / np.maximum(candidate_max, .001)
color_mask = mask & (ref_sat > .1)
brightness_ratio = float(candidate_luma[mask].mean() / ref_luma[mask].mean())
saturation_ratio = float(candidate_sat[color_mask].mean() / ref_sat[color_mask].mean())
report = {'reference': args.reference.name, 'candidate': args.candidate.name,
          'brightness_ratio': brightness_ratio, 'saturation_ratio': saturation_ratio,
          'criterion': 'Both ratios within 0.9..1.1 of accepted HIF; symptom guard only, not color fidelity certification',
          'passed': .9 <= brightness_ratio <= 1.1 and .9 <= saturation_ratio <= 1.1}
print(json.dumps(report, indent=2))
raise SystemExit(0 if report['passed'] else 1)
